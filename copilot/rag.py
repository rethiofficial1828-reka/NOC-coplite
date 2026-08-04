import os
import glob
import numpy as np

from config.settings import DOCS_DIR, INDEX_PATH, CHUNKS_PATH


# Simple pure-python TF-IDF retriever to run 100% offline without downloading models
class TFIDFRetriever:
    def __init__(self, chunks, sources):
        self.chunks = chunks
        self.sources = sources
        self.stopwords = {"the", "a", "an", "in", "on", "to", "of", "and", "is", "for", "with", "at", "by", "from", "up", "or", "as", "be", "this", "that", "these", "those"}
        
        # Tokenize chunks
        self.tokenized_chunks = [self._tokenize(c) for c in chunks]
        
        # Build vocabulary
        self.vocab = {}
        for tc in self.tokenized_chunks:
            for word in tc:
                if word not in self.vocab:
                    self.vocab[word] = len(self.vocab)
                    
        # Compute IDF
        self.N = len(chunks)
        self.idf = {}
        for word, idx in self.vocab.items():
            doc_count = sum(1 for tc in self.tokenized_chunks if word in tc)
            self.idf[word] = np.log((1 + self.N) / (1 + doc_count)) + 1
            
        # Compute TF-IDF vectors for chunks
        self.chunk_vectors = []
        for tc in self.tokenized_chunks:
            vec = np.zeros(len(self.vocab))
            for word in tc:
                vec[self.vocab[word]] += 1
            # Multiply by IDF
            for word, count in zip(self.vocab.keys(), vec):
                if count > 0:
                    vec[self.vocab[word]] = count * self.idf[word]
            # Normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            self.chunk_vectors.append(vec)

    def _tokenize(self, text):
        # Convert to lower case, keep alphanumeric characters, and remove stopwords
        words = text.lower().replace("-", " ").replace(":", " ").replace(",", " ").replace(".", " ").split()
        return [w for w in words if w not in self.stopwords and len(w) > 1]

    def retrieve(self, query, k=3):
        query_words = self._tokenize(query)
        if not query_words or not self.vocab:
            # Fallback to first k chunks
            return [{"chunk": self.chunks[i], "source": self.sources[i], "score": 0.5} for i in range(min(k, len(self.chunks)))]
            
        # Compute query vector
        query_vec = np.zeros(len(self.vocab))
        for word in query_words:
            if word in self.vocab:
                query_vec[self.vocab[word]] += 1
                
        for word in self.vocab.keys():
            if query_vec[self.vocab[word]] > 0:
                query_vec[self.vocab[word]] = query_vec[self.vocab[word]] * self.idf[word]
                
        q_norm = np.linalg.norm(query_vec)
        if q_norm > 0:
            query_vec = query_vec / q_norm
            
        # Compute cosine similarities
        scores = []
        for idx, cv in enumerate(self.chunk_vectors):
            similarity = float(np.dot(cv, query_vec))
            scores.append((similarity, idx))
            
        # Sort descending by similarity
        scores.sort(reverse=True, key=lambda x: x[0])
        
        results = []
        for score, idx in scores[:k]:
            results.append({
                "chunk": self.chunks[idx],
                "source": self.sources[idx],
                "score": score
            })
        return results

class LocalRAG:
    def __init__(self):
        self.chunks = []
        self.sources = []
        self.fallback_retriever = None
        self.model = None
        self.index = None
        
        # Load chunks first
        if os.path.exists(CHUNKS_PATH):
            self.load_chunks()
        else:
            self.read_raw_documents()
            
        # Attempt to load SentenceTransformer for neural search
        # If it fails, hangs, or is set to offline, we fall back to the TF-IDF retriever
        try:
            # Try to load cached model from disk if it already exists,
            # but we set a short timeout/check to see if Hugging Face is reachable
            # or if we can instantiate it quickly.
            # To be absolutely safe and prevent hanging, we can use a flag:
            USE_NEURAL = os.environ.get("NOC_USE_NEURAL", "false").lower() == "true"
            if USE_NEURAL:
                from sentence_transformers import SentenceTransformer
                import faiss
                print("Initializing Neural SentenceTransformer model (all-MiniLM-L6-v2)...")
                self.model = SentenceTransformer("all-MiniLM-L6-v2")
                self.dimension = 384
                if os.path.exists(INDEX_PATH):
                    self.index = faiss.read_index(INDEX_PATH)
                else:
                    self.build_faiss_index()
            else:
                print("Using high-performance Offline TF-IDF Keyword Retriever.")
                self.fallback_retriever = TFIDFRetriever(self.chunks, self.sources)
        except Exception as e:
            print(f"Neural retriever init failed: {e}. Falling back to TF-IDF.")
            self.fallback_retriever = TFIDFRetriever(self.chunks, self.sources)

    def read_raw_documents(self):
        txt_files = glob.glob(os.path.join(DOCS_DIR, "*.txt"))
        all_chunks = []
        all_sources = []
        
        for file_path in txt_files:
            filename = os.path.basename(file_path)
            with open(file_path, "r") as f:
                content = f.read()
                
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            for p in paragraphs:
                lines = [line.strip() for line in p.split("\n") if line.strip()]
                if len(lines) > 1 and lines[0].endswith(":"):
                    all_chunks.append(p)
                    all_sources.append(filename)
                else:
                    for line in lines:
                        if len(line) > 20:
                            all_chunks.append(line)
                            all_sources.append(filename)
                            
        self.chunks = all_chunks
        self.sources = all_sources
        
        # Save chunks on disk so we don't parse raw text every time
        os.makedirs(os.path.dirname(CHUNKS_PATH), exist_ok=True)
        with open(CHUNKS_PATH, "w") as f:
            for chunk, src in zip(self.chunks, self.sources):
                f.write(f"SOURCE:{src}\nCONTENT:{chunk}\n\n")

    def load_chunks(self):
        self.chunks = []
        self.sources = []
        with open(CHUNKS_PATH, "r") as f:
            content = f.read()
            blocks = content.split("\n\n")
            for block in blocks:
                lines = block.split("\n")
                if len(lines) >= 2 and lines[0].startswith("SOURCE:") and lines[1].startswith("CONTENT:"):
                    self.sources.append(lines[0][7:])
                    self.chunks.append("\n".join([lines[1][8:]] + lines[2:]))

    def build_faiss_index(self):
        import faiss
        print("Building FAISS index...")
        embeddings = self.model.encode(self.chunks, show_progress_bar=False)
        embeddings = np.array(embeddings).astype("float32")
        self.index = faiss.IndexFlatIP(self.dimension)
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        faiss.write_index(self.index, INDEX_PATH)
        print("FAISS index saved.")

    def retrieve(self, query, k=3):
        if self.fallback_retriever:
            return self.fallback_retriever.retrieve(query, k)
            
        if self.index is None or not self.chunks:
            # Fall back to TF-IDF if index is not loaded
            self.fallback_retriever = TFIDFRetriever(self.chunks, self.sources)
            return self.fallback_retriever.retrieve(query, k)
            
        import faiss
        query_vector = self.model.encode([query])
        query_vector = np.array(query_vector).astype("float32")
        faiss.normalize_L2(query_vector)
        distances, indices = self.index.search(query_vector, k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.chunks):
                results.append({
                    "chunk": self.chunks[idx],
                    "source": self.sources[idx],
                    "score": float(distances[0][i])
                })
        return results

if __name__ == "__main__":
    # Test index creation and retrieval
    rag = LocalRAG()
    test_query = "congestion on Branch3 MPLS Link"
    print(f"\nTest retrieval for query: '{test_query}':")
    matches = rag.retrieve(test_query, k=2)
    for idx, match in enumerate(matches):
        print(f"\n[{idx+1}] Score: {match['score']:.4f} | Source: {match['source']}")
        print(match['chunk'])
