import { createSignal, onMount } from "solid-js";
import { isServer } from "solid-js/web";
import { Button } from "~/components/ui/button";

export default function FontToggle() {
  const [serif, setSerif] = createSignal(false);

  onMount(() => {
    const stored = localStorage.getItem("blog-font-preference");
    if (stored === "serif") setSerif(true);
  });

  const toggle = () => {
    if (isServer) return;
    const next = !serif();
    setSerif(next);
    localStorage.setItem("blog-font-preference", next ? "serif" : "sans");
    document.documentElement.classList.toggle("blog-serif", next);
  };

  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label={`Switch to ${serif() ? "sans-serif" : "serif"} font`}>
      <span class="text-sm font-medium">Aa</span>
    </Button>
  );
}
