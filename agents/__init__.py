"""
Multi-Agent Package for AI Video & Storyteller Automation:
1. topic-agent (TopicAgent): Deep research from web and multi-source synthesis
2. content-analyser (ContentAnalyserAgent): Fact-checking, grammar, pacing & script correction
3. image-generator (ImageGeneratorAgent): Deep image search, source verification, topic matching & auto-replacement
4. Verify-video (VerifyVideoAgent): End-to-end verification of research, content, images, audio & final video
"""

from agents.topic_agent import TopicAgent
from agents.content_analyser import ContentAnalyserAgent
from agents.image_generator import ImageGeneratorAgent
from agents.verify_video import VerifyVideoAgent
from agents.orchestrator import MultiAgentOrchestrator

__all__ = [
    "TopicAgent",
    "ContentAnalyserAgent",
    "ImageGeneratorAgent",
    "VerifyVideoAgent",
    "MultiAgentOrchestrator",
]

