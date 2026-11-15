"use client";

import { useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PaperCockpit } from "@/features/paper/components/PaperCockpit";

import { PaperArchive } from "./PaperArchive";

export default function PaperPage() {
  const [tab, setTab] = useState("cockpit");
  return (
    <Tabs value={tab} onValueChange={setTab} className="flex min-w-0 flex-col">
      <TabsList className="mb-3 w-auto self-start" aria-label="Paper trading views">
        <TabsTrigger value="cockpit">Live cockpit</TabsTrigger>
        <TabsTrigger value="archive">Archived sessions</TabsTrigger>
      </TabsList>
      <TabsContent value="cockpit" className="mt-0">
        <PaperCockpit />
      </TabsContent>
      <TabsContent value="archive" className="mt-0">
        <PaperArchive />
      </TabsContent>
    </Tabs>
  );
}
