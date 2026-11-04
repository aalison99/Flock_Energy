import type { components } from "../../generated/schema";

export type BBoxResponse = components["schemas"]["BBoxResponse"];
export type BBoxMeter = components["schemas"]["BBoxMeter"];
export type NearResponse = components["schemas"]["NearResponse"];
export type NearMeter = components["schemas"]["NearMeter"];

export interface Bounds {
  min_lat: number;
  min_lng: number;
  max_lat: number;
  max_lng: number;
}

export interface NearQuery {
  lat: number;
  lng: number;
  radius_km: number;
}
