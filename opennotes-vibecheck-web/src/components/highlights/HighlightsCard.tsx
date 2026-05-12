import {
  createEffect,
  createSignal,
  For,
  onCleanup,
  Show,
  type JSX,
} from "solid-js";
import Autoplay from "embla-carousel-autoplay";
import EmblaSSR from "embla-carousel-ssr";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from "@opennotes/ui/components/ui/carousel";

type EmblaInstance = ReturnType<NonNullable<CarouselApi>>;
import { ProgressCircle } from "@opennotes/ui/components/ui/progress-circle";
import { useHighlights } from "./HighlightsStoreProvider";

export const HIGHLIGHTS_AUTOPLAY_MS = 5000;

export function HighlightsCard(): JSX.Element | null {
  const store = useHighlights();
  const items = () => store.items();

  const [api, setApi] = createSignal<EmblaInstance | undefined>(undefined);
  const [progress, setProgress] = createSignal(0);

  const autoplay = Autoplay({ delay: HIGHLIGHTS_AUTOPLAY_MS });
  const ssrPlugin = EmblaSSR();

  createEffect(() => {
    const emblaApi = api();
    if (!emblaApi) return;

    emblaApi.plugins()?.autoplay?.play();

    let rafId: number;

    function tick() {
      const embla = api();
      if (!embla) return;

      const autoplayPlugin = embla.plugins()?.autoplay;
      if (!autoplayPlugin) {
        setProgress(0);
        rafId = requestAnimationFrame(tick);
        return;
      }

      if (!autoplayPlugin.isPlaying()) {
        setProgress(0);
        rafId = requestAnimationFrame(tick);
        return;
      }

      const timeLeft = autoplayPlugin.timeUntilNext();
      if (timeLeft === null || timeLeft <= 0) {
        setProgress(0);
      } else {
        const pct = Math.round(
          ((HIGHLIGHTS_AUTOPLAY_MS - timeLeft) / HIGHLIGHTS_AUTOPLAY_MS) * 100,
        );
        setProgress(Math.min(100, Math.max(0, pct)));
      }

      rafId = requestAnimationFrame(tick);
    }

    rafId = requestAnimationFrame(tick);
    onCleanup(() => cancelAnimationFrame(rafId));
  });

  return (
    <Show when={items().length > 0} fallback={null}>
      <section
        data-testid="highlights-card"
        class="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-sm"
      >
        <Carousel
          opts={{ loop: true }}
          plugins={[autoplay, ssrPlugin]}
          setApi={setApi}
        >
          <CarouselContent>
            <For each={items()}>
              {(item) => (
                <CarouselItem>
                  <div
                    data-testid="highlight-slide"
                    class="flex flex-col gap-1"
                  >
                    <p class="text-sm font-semibold leading-snug">{item.title}</p>
                    <Show when={item.detail}>
                      <p class="text-xs text-muted-foreground">{item.detail}</p>
                    </Show>
                  </div>
                </CarouselItem>
              )}
            </For>
          </CarouselContent>

          <Show when={items().length > 1}>
            <div class="mt-3 flex items-center justify-end gap-1">
              <ProgressCircle
                data-testid="highlights-progress"
                value={progress()}
                size="xs"
                showAnimation={false}
              />
              <CarouselPrevious
                data-testid="highlights-prev"
                class="relative left-auto top-auto translate-y-0"
              />
              <CarouselNext
                data-testid="highlights-next"
                class="relative right-auto top-auto translate-y-0"
              />
            </div>
          </Show>
        </Carousel>
      </section>
    </Show>
  );
}
