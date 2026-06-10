declare module "cytoscape-node-html-label" {
  import type cytoscape from "cytoscape";

  interface CytoscapeNodeHtmlParams {
    query?: string;
    halign?: "left" | "center" | "right";
    valign?: "top" | "center" | "bottom";
    halignBox?: "left" | "center" | "right";
    valignBox?: "top" | "center" | "bottom";
    cssClass?: string;
    tpl?: (d: any) => string;
  }

  interface CytoscapeContainerParams {
    enablePointerEvents?: boolean;
  }

  function cytoscapeNodeHtmlLabel(
    cy: typeof cytoscape,
    params: CytoscapeNodeHtmlParams[],
    options?: CytoscapeContainerParams,
  ): void;

  export default cytoscapeNodeHtmlLabel;
}
