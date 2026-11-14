import {useId} from 'react';
import {Background, Controls, MarkerType, ReactFlow} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

type GraphNode = {id: string; label: string; x: number; y: number; kind?: string};
export function Graph({nodes, edges, label}: {
  nodes: GraphNode[];
  edges: {source: string; target: string}[];
  label: string;
}) {
  const id = useId();
  return <div className="graph" role="region" aria-label={label}>
    <ReactFlow id={id}
      nodes={nodes.map(node => ({
        id: node.id, data: {label: node.label},
        position: {x: node.x, y: node.y},
        className: `service-node node-${node.kind ?? 'candidate'}`,
      }))}
      edges={edges.map((edge, index) => ({...edge, id: String(index)}))}
      defaultMarkerColor="var(--graph-edge)"
      defaultEdgeOptions={{style: {stroke: 'var(--graph-edge)', strokeWidth: 1.6}, markerEnd: {type: MarkerType.ArrowClosed}}}
      fitView fitViewOptions={{padding: .2, maxZoom: 1.15}}
      nodesDraggable={false} nodesConnectable={false} nodesFocusable={false}
      zoomOnScroll={false} zoomOnPinch panOnDrag
    ><Background gap={19} size={1} color="var(--graph-dot)"/><Controls showInteractive={false}/></ReactFlow>
  </div>;
}

export function Topology({nodes, edges}: {
  nodes: {id: string; kind: string}[];
  edges: {source: string; target: string}[];
}) {
  const levels: Record<string, number> = {gateway: 0, api: 1, inventory: 2, payment: 2, worker: 2, redis: 3, db: 3};
  const labels: Record<string, string> = {gateway: 'Gateway', inventory: 'Inventory', payment: 'Mock payment', worker: 'Notification worker', redis: 'Redis cache', db: 'PostgreSQL'};
  const positioned = [0, 1, 2, 3].flatMap(level => {
    const row = nodes.filter(node => (levels[node.kind] ?? 2) === level);
    return row.map((node, column) => ({
      ...node,
      label: node.kind === 'api' ? `Checkout API ${node.id.split('-').at(-1)}` : labels[node.kind] ?? node.id,
      x: (column - (row.length - 1) / 2) * 207,
      y: level * 105,
    }));
  });
  return <Graph nodes={positioned} edges={edges} label="Architecture graph"/>;
}
