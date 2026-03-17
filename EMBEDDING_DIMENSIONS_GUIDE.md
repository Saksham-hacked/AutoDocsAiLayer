# Gemini Embedding Model Dimension Reference

## Available Models and Their Dimensions

### Option 1: text-embedding-004 (RECOMMENDED for most use cases)
- **Model Name**: `models/text-embedding-004`
- **Dimensions**: 768 (default)
- **Can be reduced to**: 256, 512, or any custom dimension
- **Best for**: Storage efficiency, faster retrieval, general-purpose embeddings
- **Status**: Currently available and stable

### Option 2: gemini-embedding-001 (Higher quality)
- **Model Name**: `gemini-embedding-001`
- **Dimensions**: 3072 (default)
- **Can be reduced to**: 768, 1536, or any custom dimension using `output_dimensionality`
- **Best for**: Highest quality embeddings when storage isn't a concern
- **Status**: Generally available
- **Note**: 4x larger storage requirement than text-embedding-004

### Option 3: gemini-embedding-2-preview (Experimental, Multimodal)
- **Model Name**: `gemini-embedding-2-preview`
- **Dimensions**: 3072 (default)
- **Features**: Supports text, images, video, audio, and PDFs
- **Best for**: Multimodal embeddings
- **Status**: Experimental/Preview
- **Note**: Embedding space incompatible with gemini-embedding-001

## Current Configuration in autodocs-layer2

The migration uses:
```env
GEMINI_EMBED_MODEL_NAME=models/text-embedding-004
EMBEDDING_DIM=768
```

This is correct! ✅

## If You Want Higher Quality (3072 dimensions)

Update your `.env` file:
```env
GEMINI_EMBED_MODEL_NAME=gemini-embedding-001
EMBEDDING_DIM=3072
```

Then update the database schema:
```bash
# Drop existing table
psql $PG_DSN -c "DROP TABLE IF EXISTS summaries;"

# Recreate with new dimension
# Edit app/schema/create_tables.sql first:
# Change: embedding vector(1536)
# To:     embedding vector(3072)

psql $PG_DSN -f app/schema/create_tables.sql
```

## Recommendation

**Stick with text-embedding-004 (768 dims)** because:
- 4x less storage space
- Faster similarity search  
- Still excellent quality
- More cost-effective
- According to Google's benchmarks, 768 dimensions achieve comparable performance to 3072 dimensions for most tasks

## Performance Comparison (from Google's MTEB benchmark)

| Dimensions | Quality Score | Storage | Speed |
|------------|---------------|---------|-------|
| 256        | Good          | Minimal | Fastest |
| 768        | Excellent     | Low     | Fast |
| 1536       | Excellent     | Medium  | Medium |
| 3072       | Excellent     | High    | Slower |

The sweet spot is **768 dimensions** for most production use cases.
