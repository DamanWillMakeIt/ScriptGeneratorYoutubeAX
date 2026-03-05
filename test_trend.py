import asyncio
from dotenv import load_dotenv
from app.agents.trend_hunter import TrendHunterAgent

# Load your API keys
load_dotenv()

async def main():
    print("🚀 Initializing The Architect...")
    
    # Initialize the Agent
    agent = TrendHunterAgent()
    
    # Run the hunt
    niche = "Day in the life of a software engineer"
    print(f"🎯 Hunting for viral trends in: '{niche}'...\n")
    
    result = await agent.find_viral_topic(niche)
    
    print("\n" + "="*40)
    print("✅ WINNING TOPIC FOUND")
    print("="*40)
    print(f"🏆 TOPIC: {result.get('topic')}")
    print(f"🔥 VIRAL SCORE (Velocity): {result.get('viral_score')}")
    print(f"⚔️ COMPETITORS TO MODEL:")
    for url in result.get('competitors', []):
        print(f"   - {url}")
    print("="*40)

if __name__ == "__main__":
    asyncio.run(main())