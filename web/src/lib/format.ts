/** Numbers as Vietnamese readers write them (a point between thousands, a comma for decimals), formatted once here so
 * no screen keeps its own copy. */
export const countFormat = new Intl.NumberFormat("vi-VN");
/** At most one decimal: seconds, a speed, a ratio. */
export const decimalFormat = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
export const percentFormat = new Intl.NumberFormat("vi-VN", { style: "percent", maximumFractionDigits: 1 });

export const formatCount = (value: number): string => countFormat.format(value);
export const formatTrimmed = (value: number): string => decimalFormat.format(value);
