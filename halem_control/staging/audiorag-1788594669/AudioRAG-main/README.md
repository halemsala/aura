# AudioRAG
Audio RAG pipeline for speech transcription, timestamped chunking, embeddings, and retrieval-augmented querying.

This repository provides a small pipeline to:
- Transcribe audio using OpenAI Whisper (local)
- Generate an audio-level caption describing the recording (using Mistral Voxtral)
- Split the transcript into timestamped chunks and embed them with Mistral embeddings
- Store chunks in ChromaDB for retrieval
- Run queries against the stored audio and get concise answers grounded in audio chunks

Files
- [build_rag.py](build_rag.py): Build the RAG index from an audio file (transcribe → chunk → embed → store).
- [query_rag.py](query_rag.py): Query the Chroma-backed RAG index and generate an answer using Mistral.
- [transcribeRAG.py](transcribeRAG.py): Minimal Whisper transcription example showing word timestamps.
- [whisper_RAG_example.py](whisper_RAG_example.py): Another Whisper example that can download a test clip and transcribe it.

Requirements
- Python 3.8+
- Packages (example): `whisper`, `torch`, `requests`, `python-dotenv`, `chromadb`, `mistralai` (Mistral client), `base64` (std lib)

Quick install
```bash
python -m pip install -r requirements.txt
# If you don't have a requirements file, install manually e.g.: 
pip install git+https://github.com/openai/whisper.git torch requests python-dotenv chromadb mistralai
```

Environment
- Create a `.env` file in the project root with your Mistral API key:

MISTRAL_API_KEY=your_mistral_api_key_here

Notes:
- `build_rag.py` and `query_rag.py` require a valid `MISTRAL_API_KEY` in the environment.
- Chroma persistent DB is stored in `./chroma_db` by default.

Usage

1) Build the audio RAG index

Run the pipeline to transcribe, caption, chunk, embed, and store in Chroma:

```bash
python build_rag.py
```

Key options and behavior (in `build_rag.py`):
- `transcribe_audio(audio_path, model_size="tiny")`: uses Whisper local model (`tiny` by default). Produces a list of timestamped segments.
- `create_chunks(segments, chunk_duration=20, overlap=2)`: groups segments into chunks ~`chunk_duration` seconds long with `overlap` seconds of overlap. Adjust to tune chunk size.
- `generate_audio_caption(audio_path, model="voxtral-mini-latest")`: generates a single high-level caption/description for the audio using Mistral Voxtral.
- `embed_chunks(chunks, audio_caption)`: uses the Mistral embedding model `mistral-embed` to embed chunk text with the audio caption as context.
- `store_in_chroma(...)`: stores `ids`, `documents`, `embeddings`, and `metadatas` into the `audio_rag` collection.

Outputs
- The script prints progress and returns `(enriched_chunks, audio_caption)` when run programmatically.
- Chroma DB is populated at `./chroma_db` and contains per-chunk metadata including `start`, `end`, `timestamp`, `transcript`, and `audio_caption`.

2) Query the RAG index

Use `query_rag.py` to ask questions grounded in the audio transcript chunks.

```bash
python query_rag.py
# or import and call: from query_rag import query_rag; query_rag("what is being discussed?")
```

Behavior (in `query_rag.py`):
- The script encodes the query using `mistral-embed` and queries the `audio_rag` collection for the top-k similar chunks (default `top_k=3`).
- It prints the retrieved chunk timestamps and short transcript preview, then forms a prompt combining the retrieved chunks and the user's question.
- It calls `mistral_client.chat.complete` (with `mistral-small-latest`) to produce a concise answer grounded in the chunks.

3) Local Whisper transcription examples

- `transcribeRAG.py`: simple example demonstrating Whisper local transcription and printing word timestamps. Useful for inspecting the raw transcript and timestamps.
- `whisper_RAG_example.py`: same idea, with a helper to download a sample audio clip when none is present.

Running the Whisper examples
```bash
python transcribeRAG.py
python whisper_RAG_example.py
```

Tips & Troubleshooting
- Model downloads sometimes fail due to network/SSL issues; both Whisper examples include a small SSL workaround to ignore certificate verification for downloads. Use at your own risk and restore strict verification for production.
- If Whisper is slow, install a GPU-compatible PyTorch build matching your CUDA version.
- Ensure `MISTRAL_API_KEY` is set before running `build_rag.py` and `query_rag.py`.
- If you change `chunk_duration` / `overlap`, re-run `build_rag.py` to rebuild the index.
