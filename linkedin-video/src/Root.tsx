import React from "react";
import { Composition } from "remotion";
import { JobPilotV4Video } from "./JobPilotV4Video";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="JobPilotV4"
        component={JobPilotV4Video}
        durationInFrames={720}
        fps={30}
        width={1080}
        height={1350}
        defaultProps={{}}
      />
    </>
  );
};
