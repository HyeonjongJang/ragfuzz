import glob
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

def load_docs():
    docs=[]
    for p in glob.glob("rag/index/raw/*"):
        docs+=TextLoader(p, encoding="utf-8").load()
    return docs

if __name__=="__main__":
    docs=load_docs()
    if not docs:
        from langchain.schema import Document
        docs=[Document(page_content="JSON boundary cases, control chars, nesting depth, long strings")]
    splitter=RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks=splitter.split_documents(docs)
    try:
        embs=OpenAIEmbeddings(model="text-embedding-3-large")
        db=FAISS.from_documents(chunks, embs)
        db.save_local("rag/index/faiss")
    except Exception:
        pass
