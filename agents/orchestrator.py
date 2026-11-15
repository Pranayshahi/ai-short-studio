"""
Multi-Agent Orchestrator connecting the 4 core agents:
1. topic-agent (TopicAgent)          -> Deep web & source research on topic
2. content-analyser (ContentAnalyserAgent) -> Checks, fact-verifies & corrects text from topic-agent
3. image-generator (ImageGeneratorAgent)   -> Deep image search, source provenance check, topic matching & CHANGE_IMAGE loop
4. Verify-video (VerifyVideoAgent)         -> End-to-end verification of all stages, assets, audio, subtitles & rendered video
"""

from pathlib import Path
from typing import Dict, Any, Optional

from agents.topic_agent import TopicAgent
from agents.content_analyser import ContentAnalyserAgent
from agents.image_generator import ImageGeneratorAgent
from agents.verify_video import VerifyVideoAgent
from agents.music_agent import MusicAgent
from agents.hindi_voice_agent import HindiVoiceAgent


class MultiAgentOrchestrator:
    """
    Coordinates the autonomous agents workflow:
    topic-agent -> content-analyser -> image-generator -> hindi-voice-agent -> music-agent -> Verify-video
    """

    def __init__(self, target_width: int = 1080, target_height: int = 1920):
        self.topic_agent = TopicAgent()
        self.content_analyser = ContentAnalyserAgent()
        self.image_generator = ImageGeneratorAgent(
            target_width=target_width,
            target_height=target_height,
        )
        self.verify_video = VerifyVideoAgent(
            target_width=target_width,
            target_height=target_height,
        )
        self.music_agent = MusicAgent()
        self.hindi_voice_agent = HindiVoiceAgent()

    def run_research_and_content(
        self,
        topic: Optional[str] = None,
        style: str = "default",
        language: str = "en",
        target_duration: float = 25.0,
        custom_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs Agent 1 ('topic-agent') followed by Agent 2 ('content-analyser')."""
        topic_research = self.topic_agent.run(
            topic=topic,
            language=language,
            target_duration=target_duration,
            custom_notes=custom_notes,
        )
        content_analysis = self.content_analyser.run(
            topic_research=topic_research,
            style=style,
            target_duration=target_duration,
            language=language,
        )
        return {
            "topic_research": topic_research,
            "content_analysis": content_analysis,
        }

    def run_image_generation(
        self,
        topic_research: Dict[str, Any],
        content_analysis: Dict[str, Any],
        output_dir: Path,
        style: str = "default",
    ) -> Dict[str, Any]:
        """Runs Agent 3 ('image-generator') with source checking and topic-match replacement."""
        return self.image_generator.run(
            topic_research=topic_research,
            content_analysis=content_analysis,
            output_dir=output_dir,
            style=style,
        )

    def run_video_verification(
        self,
        project_record: Dict[str, Any],
        topic_research: Optional[Dict[str, Any]] = None,
        content_analysis: Optional[Dict[str, Any]] = None,
        image_report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Runs Agent 4 ('Verify-video') to verify all things across the pipeline."""
        return self.verify_video.run(
            project_record=project_record,
            topic_research=topic_research,
            content_analysis=content_analysis,
            image_report=image_report,
        )

