from dataclasses import dataclass, field
from typing import Any, Dict, List
from reader.json_reader import JSONReader
from embedding.embedding import BaseEmbedding
from chunking.chunking import Chunk
from rerank.rerank import BedrockReranker
from storage.db.vector.vector_storage import VectorStorage
from pydantic import BaseModel
from inferencer.inferencer import BaseInferencer

class Question(BaseModel):
    question: str
    answer: str

    def get_chunk(self) -> Chunk:
        return Chunk(data=self.question)
    

@dataclass
class RetrieverItem:
    question: str = field(default_factory=None)
    answer: str = field(default_factory=None)
    guardrails_output_assessment:List = field(default_factory=None)
    guardrails_context_assessment: List = field(default_factory=None)
    guardrails_input_assessment: List = field(default_factory=None)
    guardrails_blocked: bool = field(default_factory=False)
    answer_metadata: Dict[str, Any] = field(default_factory={})
    query_metadata: Dict[str, Any] = field(default_factory={})
    reference_contexts: List[str] = field(default_factory=[])
    gt_answer: str = field(default_factory=None)

    def to_json(self):
        return {
            "question": self.question,
            "answer": self.answer,
            "guardrails_output_assessment": self.guardrails_output_assessment,
            "guardrails_context_assessment": self.guardrails_context_assessment,
            "guardrails_input_assessment": self.guardrails_input_assessment,
            "guardrails_blocked": self.guardrails_blocked,
            "answer_metadata": self.answer_metadata,
            "query_metadata": self.query_metadata,
            "reference_contexts": self.reference_contexts,
            "gt_answer": self.gt_answer
        }

class Retriever:
    def __init__(self, json_reader: JSONReader, embedding: BaseEmbedding, vector_storage: VectorStorage, inferencer: BaseInferencer, reranker: BedrockReranker) -> None:
        self.json_reader = json_reader
        self.embedding = embedding
        self.vector_storage = vector_storage
        self.inferencer = inferencer
        self.reranker = reranker

    def retrieve(self, path: str, query: str, knn: int, hierarchical: bool = False):
        result = []
        questions_list = self.json_reader.read_as_model(path, Question)
        for question in questions_list:
            question_chunk = question.get_chunk()
            response = self.vector_storage.search(question_chunk, knn, hierarchical)
            vector_response = response.to_json()['result']
            
            if response.status:
                if self.reranker:
                    vector_response = self.reranker.rerank_documents(question_chunk.data, vector_response)
                metadata, answer = self.inferencer.generate_text(question.question, vector_response)
                guardrail_blocked = metadata['guardrail_blocked'] if 'guardrail_blocked' in metadata else False
                answer_metadata = metadata
            else:
                answer = response.metadata['guardrail_output']
                metadata = {}
                answer_metadata = {}
                guardrail_blocked = response.metadata['guardrail_blocked'] if 'guardrail_blocked' in response.metadata else False

            result.append(RetrieverItem(
                question=question.question,
                answer=answer,
                guardrails_output_assessment=metadata['guardrail_output_assessment'] if 'guardrail_output_assessment' in metadata else None,
                guardrails_context_assessment=response.metadata['guardrail_context_assessment'] if 'guardrail_context_assessment' in response.metadata else None,
                guardrails_input_assessment=response.metadata['guardrail_input_assessment'] if 'guardrail_input_assessment' in response.metadata else None,
                guardrails_blocked=guardrail_blocked,
                answer_metadata=answer_metadata,
                reference_contexts=[res['text'] for res in vector_response] if vector_response else [],
                gt_answer=question.answer,
                query_metadata=response.metadata['embedding_metadata'].to_json() if 'embedding_metadata' in response.metadata else None
            ))

        return result
            
            