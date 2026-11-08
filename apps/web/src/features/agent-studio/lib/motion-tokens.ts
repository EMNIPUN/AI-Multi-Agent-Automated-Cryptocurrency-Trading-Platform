/** Shared Motion tokens — prefer transform/opacity (compositor-friendly). */
export const studioSpring = {
  type: "spring" as const,
  stiffness: 380,
  damping: 32,
  mass: 0.8,
};

export const studioSoftSpring = {
  type: "spring" as const,
  stiffness: 260,
  damping: 28,
  mass: 0.9,
};

export const studioFade = {
  duration: 0.28,
  ease: [0.22, 1, 0.36, 1] as const,
};

export const studioStagger = {
  delayChildren: 0.06,
  staggerChildren: 0.05,
};
