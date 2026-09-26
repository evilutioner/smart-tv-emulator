"use strict";
export const $ = id => document.getElementById(id);
export function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}
export async function api(path, method = "POST", body = {}) {
  const result = await fetch(`/api/v1/${path}`, {method, headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if (!result.ok) {
    // Carry the whole body: some refusals are answers in their own right, not faults,
    // and the caller decides how to present one.
    let data = {}; try { data = await result.json(); } catch {}
    const error = new Error(data.error || `HTTP ${result.status}`);
    error.status = result.status; error.body = data;
    throw error;
  }
  return result.json();
}
