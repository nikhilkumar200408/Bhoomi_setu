"""Document AI: indexing, retrieval, cited QA, quote verification, contradiction and amendment detection.

Everything here is deterministic and extractive: answers are exact passages from the indexed
documents, and every citation is re-checked against the stored page text by the backend.
No language model is used, so nothing can be paraphrased into a fabricated quote.
"""
