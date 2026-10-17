import type { components } from "./schema";

type Schemas = components["schemas"];

export type PlanRequest = Schemas["PlanRequest"];
export type PlanResponse = Schemas["PlanResponse"];
export type GeocodeResponse = Schemas["GeocodeResponse"];
export type Place = Schemas["Place"];
export type Ready = Schemas["Ready"];
export type Health = Schemas["Health"];
export type RiskLevel = Schemas["RiskLevelEnum"];
