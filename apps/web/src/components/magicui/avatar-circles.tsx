"use client";

import { cn } from "@/lib/utils";

interface Avatar {
  imageUrl: string;
  profileUrl?: string;
}

interface AvatarCirclesProps {
  className?: string;
  numPeople?: number;
  avatarUrls: Avatar[];
}

export function AvatarCircles({ numPeople, className, avatarUrls }: AvatarCirclesProps) {
  return (
    <div className={cn("z-10 flex -space-x-3 rtl:space-x-reverse", className)}>
      {avatarUrls.map((url, index) => {
        const img = (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={index}
            className="h-9 w-9 rounded-full border-2 border-black object-cover"
            src={url.imageUrl}
            width={36}
            height={36}
            alt={`Avatar ${index + 1}`}
          />
        );
        return url.profileUrl ? (
          <a key={index} href={url.profileUrl} target="_blank" rel="noopener noreferrer">
            {img}
          </a>
        ) : (
          <span key={index}>{img}</span>
        );
      })}
      {(numPeople ?? 0) > 0 ? (
        <span className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-black bg-white text-center text-xs font-medium text-black">
          +{numPeople}
        </span>
      ) : null}
    </div>
  );
}
