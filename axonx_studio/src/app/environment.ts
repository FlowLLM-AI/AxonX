export const playground = import.meta.env.MODE === "playground";
export const assetUrl = (name: string) => `${import.meta.env.BASE_URL}${name}`;
