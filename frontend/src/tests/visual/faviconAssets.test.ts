// @ts-expect-error Vitest runs this contract in Node; app builds exclude Node globals.
import { readFileSync, statSync } from "node:fs";
import { describe, expect, it } from "vitest";

const indexHtml = readFileSync("index.html", "utf8");
const manifest = JSON.parse(
   readFileSync("public/site.webmanifest", "utf8")
) as {
   name: string;
   short_name: string;
   theme_color: string;
   background_color: string;
   icons: Array<{
      src: string;
      sizes: string;
      type: string;
      purpose: string;
   }>;
};

const faviconFiles = [
   "favicon.svg",
   "favicon-96x96.png",
   "favicon.ico",
   "apple-touch-icon.png",
   "site.webmanifest",
   "web-app-manifest-192x192.png",
   "web-app-manifest-512x512.png",
];

describe("Ludex favicon package", () => {
   it("links the complete browser icon set from the document head", () => {
      expect(indexHtml).toMatch(
         /<link\s+rel="icon"\s+type="image\/png"\s+href="\/favicon-96x96\.png"\s+sizes="96x96"\s+\/>/
      );
      expect(indexHtml).toContain(
         '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />'
      );
      expect(indexHtml).toContain(
         '<link rel="shortcut icon" href="/favicon.ico" />'
      );
      expect(indexHtml).toMatch(
         /<link\s+rel="apple-touch-icon"\s+sizes="180x180"\s+href="\/apple-touch-icon\.png"\s+\/>/
      );
      expect(indexHtml).toContain(
         '<link rel="manifest" href="/site.webmanifest" />'
      );
   });

   it("ships every referenced favicon asset as a nonempty public file", () => {
      for (const filename of faviconFiles) {
         expect(statSync(`public/${filename}`).size).toBeGreaterThan(0);
      }
   });

   it("uses Ludex install metadata and the established retro palette", () => {
      expect(manifest.name).toBe("Ludex");
      expect(manifest.short_name).toBe("Ludex");
      expect(manifest.theme_color).toBe("#000000");
      expect(manifest.background_color).toBe("#ebe4d8");
      expect(manifest.icons).toEqual([
         {
            src: "/web-app-manifest-192x192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "maskable",
         },
         {
            src: "/web-app-manifest-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
         },
      ]);
   });
});
