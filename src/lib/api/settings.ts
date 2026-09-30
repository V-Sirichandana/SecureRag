import { USE_MOCKS, request } from "./client";
import {
  defaultAI,
  defaultBilling,
  defaultGeneral,
  defaultNotifications,
  defaultSecurity,
  invoiceHistory,
} from "@/lib/mock/settings";
import { latency } from "@/lib/mock/utils";
import type {
  Invoice,
  SettingsAI,
  SettingsBilling,
  SettingsGeneral,
  SettingsNotifications,
  SettingsSecurity,
} from "@/lib/types";

export async function getGeneralSettings(): Promise<SettingsGeneral> {
  if (USE_MOCKS) {
    await latency(300, 600);
    return { ...defaultGeneral };
  }
  return request<SettingsGeneral>("/settings/general");
}

export async function saveGeneralSettings(payload: SettingsGeneral): Promise<SettingsGeneral> {
  if (USE_MOCKS) {
    await latency(500, 900);
    return payload;
  }
  return request<SettingsGeneral>("/settings/general", { method: "PUT", body: payload });
}

export async function getSecuritySettings(): Promise<SettingsSecurity> {
  if (USE_MOCKS) {
    await latency(300, 600);
    return { ...defaultSecurity };
  }
  return request<SettingsSecurity>("/settings/security");
}

export async function saveSecuritySettings(payload: SettingsSecurity): Promise<SettingsSecurity> {
  if (USE_MOCKS) {
    await latency(500, 900);
    return payload;
  }
  return request<SettingsSecurity>("/settings/security", { method: "PUT", body: payload });
}

export async function getAISettings(): Promise<SettingsAI> {
  if (USE_MOCKS) {
    await latency(300, 600);
    return { ...defaultAI };
  }
  return request<SettingsAI>("/settings/ai");
}

export async function saveAISettings(payload: SettingsAI): Promise<SettingsAI> {
  if (USE_MOCKS) {
    await latency(500, 900);
    return payload;
  }
  return request<SettingsAI>("/settings/ai", { method: "PUT", body: payload });
}

export async function getNotificationSettings(): Promise<SettingsNotifications> {
  if (USE_MOCKS) {
    await latency(300, 600);
    return { ...defaultNotifications };
  }
  return request<SettingsNotifications>("/settings/notifications");
}

export async function saveNotificationSettings(
  payload: SettingsNotifications,
): Promise<SettingsNotifications> {
  if (USE_MOCKS) {
    await latency(500, 900);
    return payload;
  }
  return request<SettingsNotifications>("/settings/notifications", {
    method: "PUT",
    body: payload,
  });
}

export async function getBillingSettings(): Promise<SettingsBilling> {
  if (USE_MOCKS) {
    await latency(300, 600);
    return { ...defaultBilling };
  }
  return request<SettingsBilling>("/settings/billing");
}

export async function saveBillingSettings(payload: SettingsBilling): Promise<SettingsBilling> {
  if (USE_MOCKS) {
    await latency(500, 900);
    return payload;
  }
  return request<SettingsBilling>("/settings/billing", { method: "PUT", body: payload });
}

export async function getInvoices(): Promise<Invoice[]> {
  if (USE_MOCKS) {
    await latency(300, 600);
    return [...invoiceHistory];
  }
  return request<Invoice[]>("/settings/billing/invoices");
}
