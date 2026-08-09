/** Dark-only per Singularity UI Guidelines v1.0 (light mode is out of system). */

export type Theme = "dark";

export function getTheme(): Theme {
  return "dark";
}

export function applyTheme(_theme: Theme = "dark"): void {
  document.documentElement.setAttribute("data-theme", "dark");
  document.documentElement.style.colorScheme = "dark";
  try {
    localStorage.removeItem("mre-theme");
  } catch {
    /* ignore */
  }
}

export function setTheme(_theme: Theme): void {
  applyTheme("dark");
}

export function toggleTheme(): Theme {
  applyTheme("dark");
  return "dark";
}
