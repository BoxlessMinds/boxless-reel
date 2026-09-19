import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import type { Artifact } from "@/types/artifacts";

interface ArtifactContextValue {
  /** Artifact currently shown in the side panel, if any. */
  activeArtifact: Artifact | null;
  /** Whether the side panel is open. */
  isOpen: boolean;
  /** Open (or replace) the artifact shown in the side panel. */
  openArtifact: (artifact: Artifact) => void;
  /** Close the side panel. */
  closeArtifact: () => void;
}

const ArtifactContext = createContext<ArtifactContextValue | null>(null);

export function ArtifactProvider({ children }: { children: React.ReactNode }) {
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const location = useLocation();

  const openArtifact = useCallback((artifact: Artifact) => {
    setActiveArtifact(artifact);
  }, []);

  const closeArtifact = useCallback(() => {
    setActiveArtifact(null);
  }, []);

  // Close the panel whenever the user navigates to a different page, since the
  // open artifact belongs to the conversation that is being left behind.
  useEffect(() => {
    setActiveArtifact(null);
  }, [location.pathname]);

  const value = useMemo<ArtifactContextValue>(
    () => ({
      activeArtifact,
      isOpen: activeArtifact !== null,
      openArtifact,
      closeArtifact,
    }),
    [activeArtifact, openArtifact, closeArtifact]
  );

  return <ArtifactContext.Provider value={value}>{children}</ArtifactContext.Provider>;
}

export function useArtifacts(): ArtifactContextValue {
  const ctx = useContext(ArtifactContext);
  if (!ctx) {
    throw new Error("useArtifacts must be used within an ArtifactProvider");
  }
  return ctx;
}
