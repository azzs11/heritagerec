"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState, type ReactNode } from "react";

import s from "./search.module.css";

export interface Step {
  key: string;
  name: string;
  value: ReactNode;
  state: "done" | "pending" | "missing";
  detail?: ReactNode;
}

/** Every step from the question to the verdict, in one line; each opens to show what it did. */
export function Pipeline({ steps }: { steps: Step[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const current = steps.find((x) => x.key === open);
  return (
    <div className={s.pipeline}>
      <ol className={s.steps}>
        {steps.map((x) => (
          <li key={x.key}>
            <button
              className={`${s.step} ${s[`step_${x.state}`]}`}
              aria-expanded={open === x.key}
              disabled={!x.detail}
              onClick={() => setOpen(open === x.key ? null : x.key)}
            >
              <span className={s.stepName}>{x.name}</span>
              <span className={s.stepValue}>{x.value}</span>
            </button>
          </li>
        ))}
      </ol>
      <AnimatePresence initial={false}>
        {current?.detail ? (
          <motion.div
            key={current.key}
            className={s.stepDetail}
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
          >
            <div className={s.stepDetailInner}>{current.detail}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
