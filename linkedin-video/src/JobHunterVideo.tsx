import React from "react";
import { Series } from "remotion";
import { Scene1Hook } from "./components/Scene1Hook";
import { Scene2Intro } from "./components/Scene2Intro";
import { Scene3Scraper } from "./components/Scene3Scraper";
import { Scene4Evaluator } from "./components/Scene4Evaluator";
import { Scene5Dashboard } from "./components/Scene5Dashboard";
import { Scene6Outro } from "./components/Scene6Outro";

export const JobHunterVideo: React.FC = () => {
  return (
    <Series>
      {/* Scene 1: The Problem Hook (4.6s) */}
      <Series.Sequence durationInFrames={140}>
        <Scene1Hook />
      </Series.Sequence>

      {/* Scene 2: The Shift / Introducing AI Job Hunter (4.6s) */}
      <Series.Sequence durationInFrames={140}>
        <Scene2Intro />
      </Series.Sequence>

      {/* Scene 3: Parallel Ingestion Engine (5.3s) */}
      <Series.Sequence durationInFrames={160}>
        <Scene3Scraper />
      </Series.Sequence>

      {/* Scene 4: AI Evaluator & Scoring Matrix (5.3s) */}
      <Series.Sequence durationInFrames={160}>
        <Scene4Evaluator />
      </Series.Sequence>

      {/* Scene 5: Mission Control Dashboard UI (4.3s) */}
      <Series.Sequence durationInFrames={130}>
        <Scene5Dashboard />
      </Series.Sequence>

      {/* Scene 6: LinkedIn Viral CTA & Author Card (3.6s) */}
      <Series.Sequence durationInFrames={110}>
        <Scene6Outro />
      </Series.Sequence>
    </Series>
  );
};
