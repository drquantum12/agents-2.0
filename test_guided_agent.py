"""
Test script for the Guided Learning Agent

This script tests the basic functionality of the agent without requiring
the full FastAPI server to be running.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.agents.core_agent import run_agent, build_agent
from app.agents.schemas import LessonPlanSchema, EvaluationSchema
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_schemas():
    """Test that the Pydantic schemas are properly defined."""
    logger.info("Testing schemas...")
    
    # Test LessonPlanSchema
    lesson_plan = LessonPlanSchema(
        topic="Photosynthesis",
        steps=[
            "Understanding what photosynthesis is",
            "Learning about chlorophyll",
            "Exploring the chemical equation"
        ]
    )
    assert lesson_plan.topic == "Photosynthesis"
    assert len(lesson_plan.steps) == 3
    logger.info("✓ LessonPlanSchema works correctly")
    
    # Test EvaluationSchema
    evaluation = EvaluationSchema(
        action="proceed",
        feedback="Great job!",
        understanding_level=8
    )
    assert evaluation.action == "proceed"
    assert evaluation.understanding_level == 8
    logger.info("✓ EvaluationSchema works correctly")


def test_agent_build():
    """Test that the agent graph can be built without errors."""
    logger.info("Testing agent build...")
    
    try:
        agent = build_agent()
        logger.info("✓ Agent built successfully")
        logger.info(f"  Agent type: {type(agent)}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to build agent: {e}")
        return False


def test_agent_run():
    """Test running the agent with a simple query."""
    logger.info("Testing agent run...")
    
    # Check if MongoDB connection is available
    mongodb_uri = os.getenv("MONGODB_CONNECTION_STRING")
    if not mongodb_uri:
        logger.warning("⚠ MONGODB_CONNECTION_STRING not set, skipping agent run test")
        return False
    
    # Check if Gemini API key is available
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.warning("⚠ GOOGLE_API_KEY not set, skipping agent run test")
        return False
    
    try:
        # Create a test user and query
        test_user = {
            "_id": "test_user_123",
            "name": "Test Student"
        }
        test_query = "Teach me about the water cycle"
        test_session_id = "test_session_guided_learning"
        
        logger.info(f"Running agent with query: '{test_query}'")
        
        # Run the agent
        response = run_agent(
            user=test_user,
            query=test_query,
            session_id=test_session_id
        )
        
        logger.info("✓ Agent ran successfully")
        logger.info(f"  Response: {response[:200]}...")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to run agent: {e}", exc_info=True)
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("GUIDED LEARNING AGENT TEST SUITE")
    logger.info("=" * 60)
    
    results = []
    
    # Test 1: Schemas
    logger.info("\n[Test 1/3] Testing Pydantic Schemas")
    try:
        test_schemas()
        results.append(("Schemas", True))
    except Exception as e:
        logger.error(f"Schema test failed: {e}")
        results.append(("Schemas", False))
    
    # Test 2: Agent Build
    logger.info("\n[Test 2/3] Testing Agent Build")
    result = test_agent_build()
    results.append(("Agent Build", result))
    
    # Test 3: Agent Run (optional, requires env vars)
    logger.info("\n[Test 3/3] Testing Agent Run")
    result = test_agent_run()
    results.append(("Agent Run", result))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        logger.info(f"{test_name:20s} {status}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    logger.info(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.warning(f"\n⚠️  {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
