import { BlurFade } from "@/components/magicui/blur-fade";

export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <BlurFade className="mb-6">
      <h1 className="font-display text-3xl tracking-tight md:text-4xl">{title}</h1>
      {description ? (
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground md:text-base">
          {description}
        </p>
      ) : null}
    </BlurFade>
  );
}
