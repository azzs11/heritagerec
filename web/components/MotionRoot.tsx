"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/**
 * One place that honours the reader's reduced-motion setting for every Motion animation. Components keep the same
 * starting styles on the server and in the browser (so pre-rendered pages match), and Motion skips the movement.
 */
export function MotionRoot({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
