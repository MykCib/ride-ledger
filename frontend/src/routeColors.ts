const commuteColors = ['#4d6b38', '#d45b3f', '#5a78a0', '#8a6e9c', '#b68c3a'];

export function routeGroupColor(groupId: string): string {
  let hash = 0;
  for (const character of groupId) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return commuteColors[hash % commuteColors.length];
}
