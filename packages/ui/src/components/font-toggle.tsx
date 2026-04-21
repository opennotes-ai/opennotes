import { createSignal, onMount } from "solid-js";
import { isServer } from "solid-js/web";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";

export default function FontToggle() {
  const [serif, setSerif] = createSignal(false);

  onMount(() => {
    const stored = localStorage.getItem("blog-font-preference");
    if (stored === "serif") {
      setSerif(true);
      document.documentElement.classList.add("blog-serif");
    }
  });

  const handleChange = (value: string | null) => {
    if (isServer || !value) return;
    const next = value === "serif";
    setSerif(next);
    localStorage.setItem("blog-font-preference", next ? "serif" : "sans");
    document.documentElement.classList.toggle("blog-serif", next);
  };

  return (
    <ToggleGroup value={serif() ? "serif" : "sans"} onChange={handleChange} aria-label="Font preference">
      <ToggleGroupItem value="sans" class="font-sans text-sm" aria-label="Sans-serif font">Aa</ToggleGroupItem>
      <ToggleGroupItem value="serif" class="font-serif text-sm" aria-label="Serif font">Aa</ToggleGroupItem>
    </ToggleGroup>
  );
}
