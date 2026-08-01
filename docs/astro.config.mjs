import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";
import starlightVersions from "starlight-versions";
import starlightCelestiaTheme from "starlight-theme-celestia";

export default defineConfig({
  site: "https://mcllerena.github.io/o-grid/",
  base: "/o-grid/",
  markdown: {
    gfm: true,
    remarkPlugins: [remarkMath],
    rehypePlugins: [rehypeKatex],
    syntaxHighlight: {
      excludeLangs: ["mermaid"],
    },
  },
  integrations: [
    starlight({
      title: "o-grid",
      customCss: ["./src/styles/katex.css"],
      head: [],
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/mcllerena/o-grid",
        },
      ],
      plugins: [
        starlightCelestiaTheme(),
        starlightVersions({
          current: { label: "Latest" },
          versions: [{ slug: "0.1.0", label: "v0.1.0" }],
        }),
      ],
      sidebar: [
        {
          label: "Start here",
          items: [{ label: "Introduction", link: "/" }],
        },
        {
          label: "Tutorials",
          items: [
            { label: "Write your first ANAREDE parser", link: "/tutorials/write-a-parser/" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "ANAREDE blocks", link: "/reference/anarede-blocks/" },
            { label: "Power system models", link: "/reference/models/" },
          ],
        },
        {
          label: "Explanation",
          items: [
            { label: "Parser architecture", link: "/explanation/parser-architecture/" },
          ],
        },
      ],
    }),
  ],
});
