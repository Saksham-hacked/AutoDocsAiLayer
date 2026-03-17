#!/usr/bin/env python3
"""
Quick test script to verify Gemini API integration works correctly.
Run this after setting GEMINI_API_KEY in your .env file.
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_llm_client():
    """Test LLM client with Gemini API"""
    print("Testing LLM Client...")
    print("-" * 50)
    
    try:
        from app.tools.llm_client import LLMClient
        
        client = LLMClient()
        
        system_prompt = "You are a helpful assistant."
        user_prompt = "Say 'Hello from Gemini!' in exactly 3 words."
        
        print(f"Model: {client.model_name}")
        print(f"Sending test prompt...")
        
        response = await client.complete(system_prompt, user_prompt, temperature=0.1)
        
        print(f"✅ LLM Response: {response}")
        print(f"Response length: {len(response)} chars")
        print()
        return True
        
    except Exception as e:
        print(f"❌ LLM Test Failed: {e}")
        print()
        return False


async def test_embedding_client():
    """Test Embedding client with Gemini API"""
    print("Testing Embedding Client...")
    print("-" * 50)
    
    try:
        from app.tools.embedding_client import EmbeddingClient
        
        client = EmbeddingClient()
        
        test_text = "This is a test document about API documentation."
        
        print(f"Model: {client.model_name}")
        print(f"Text: {test_text}")
        print(f"Generating embedding...")
        
        embedding = await client.embed(test_text)
        
        print(f"✅ Embedding generated successfully")
        print(f"Dimension: {len(embedding)}")
        print(f"First 5 values: {embedding[:5]}")
        print()
        return True
        
    except Exception as e:
        print(f"❌ Embedding Test Failed: {e}")
        print()
        return False


async def main():
    print("=" * 50)
    print("Gemini API Integration Test")
    print("=" * 50)
    print()
    
    # Check for API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment")
        print("Please set it in your .env file")
        return
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    print()
    
    # Run tests
    llm_ok = await test_llm_client()
    embed_ok = await test_embedding_client()
    
    # Summary
    print("=" * 50)
    print("Test Summary")
    print("=" * 50)
    print(f"LLM Client:       {'✅ PASS' if llm_ok else '❌ FAIL'}")
    print(f"Embedding Client: {'✅ PASS' if embed_ok else '❌ FAIL'}")
    print()
    
    if llm_ok and embed_ok:
        print("🎉 All tests passed! Migration successful.")
    else:
        print("⚠️  Some tests failed. Check error messages above.")


if __name__ == "__main__":
    asyncio.run(main())
