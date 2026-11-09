import type { Citation, Conversation } from "@/lib/types";
import { iso } from "./utils";

const citationsLeave: Citation[] = [
  {
    index: 1,
    documentId: "doc_handbook",
    documentName: "Employee Handbook.pdf",
    collectionName: "HR",
    pageNumber: 14,
    quote: "Full-time employees are entitled to 20 days of annual leave per calendar year.",
  },
  {
    index: 2,
    documentId: "doc_hr_policy",
    documentName: "HR Policy.pdf",
    collectionName: "HR",
    pageNumber: 3,
    quote:
      "Employees must submit leave requests at least 3 days before the intended leave date.",
  },
];

const citationsSecurity: Citation[] = [
  {
    index: 1,
    documentId: "doc_security",
    documentName: "Security Policy.pdf",
    collectionName: "Security",
    pageNumber: 8,
    quote:
      "Access to production systems is granted through role-based access control.",
  },
  {
    index: 2,
    documentId: "doc_incident",
    documentName: "Incident Response Playbook.pdf",
    collectionName: "Security",
    pageNumber: 4,
    quote:
      "Severity 1 incidents affect all customers and require an immediate page to the on-call engineer.",
  },
];

export const demoAnswers: { match: RegExp; content: string; citations: Citation[] }[] = [
  {
    match: /leave|vacation|holiday|pto/i,
    content: `According to the employee handbook, full-time employees are entitled to **20 days of annual leave** per calendar year, in addition to locally observed public holidays. [1]

Requests must be submitted through the HR portal **at least 3 days before** the intended leave date. Your direct manager approves the request and it is recorded automatically in the HR system. [2]

A few additional details worth knowing:

- Up to **5 unused days** carry over into the next calendar year and expire at the end of March.
- Sick leave (14 days) is tracked separately and is never deducted from annual leave.
- Parental leave is 16 weeks fully paid for primary caregivers.

If you need to book time off in the next week, flag it with your manager directly — the 3-day notice window is the only hard requirement.`,
    citations: citationsLeave,
  },
  {
    match: /security|access|mfa|permission|rbac/i,
    content: `Access to production systems is governed by **role-based access control**, and every privilege is reviewed quarterly by the security team. [1]

Multi-factor authentication is mandatory for all internal applications, and service accounts must use rotating credentials stored in the secrets manager.

For incidents, the playbook defines clear severity targets:

1. **Severity 1** — page the on-call engineer immediately with a 15 minute acknowledgement target.
2. **Severity 2** — respond within 1 hour during business hours.
3. **Severity 3** — next business day.

All permission changes are written to the audit log and retained for 400 days. [2]`,
    citations: citationsSecurity,
  },
  {
    match: /expense|budget|revenue|cash|financ/i,
    content: `Operating expenses for the quarter totalled **$4.82M**, an increase of 8.4% year over year, driven mainly by cloud infrastructure and engineering headcount. [1]

Cloud spend dropped 12% after moving to reserved instances, which offset part of that growth.

The company closed the quarter with **$31.6M in cash and equivalents**, giving roughly 26 months of runway at the current burn rate. [2]

\`\`\`json
{
  "quarter": "Q3",
  "operating_expenses_usd": 4820000,
  "yoy_change_pct": 8.4,
  "cash_on_hand_usd": 31600000,
  "runway_months": 26
}
\`\`\`

Happy to break this down by cost centre if that's useful.`,
    citations: [
      {
        index: 1,
        documentId: "doc_financial",
        documentName: "Financial Report.pdf",
        collectionName: "Finance",
        pageNumber: 22,
        quote: "Operating expenses for the quarter totalled $4.82M.",
      },
      {
        index: 2,
        documentId: "doc_financial",
        documentName: "Financial Report.pdf",
        collectionName: "Finance",
        pageNumber: 23,
        quote: "closed the quarter with $31.6M in cash and equivalents",
      },
    ],
  },
];

export const fallbackAnswer: { content: string; citations: Citation[] } = {
  content: `I searched the organization's knowledge base but couldn't find a passage that directly answers this question.

Here is what I *was* able to retrieve that may be related:

- The **Employee Handbook** covers working hours, leave and sick leave policies.
- The **Security Policy** documents access control and data classification.
- The **Financial Report** contains quarterly operating expense detail.

Try rephrasing with a specific document or topic — for example *"What is the annual leave policy?"* or *"Summarise Q3 operating expenses"*.

> Demo response — the retrieval pipeline is mocked until the FastAPI backend is connected.`,
  citations: [],
};

export function answerFor(question: string): { content: string; citations: Citation[] } {
  const hit = demoAnswers.find((entry) => entry.match.test(question));
  return hit ? { content: hit.content, citations: hit.citations } : fallbackAnswer;
}

export const conversations: Conversation[] = [
  {
    id: "conv_leave",
    title: "Leave policy",
    collectionId: "col_hr",
    updatedAt: iso({ hours: 3 }),
    messageCount: 4,
    messages: [
      {
        id: "m1",
        role: "user",
        content: "How many days of annual leave do we get, and how far in advance must I request it?",
        createdAt: iso({ hours: 3 }),
      },
      {
        id: "m2",
        role: "assistant",
        content: `According to the employee handbook, full-time employees are entitled to **20 days of annual leave** per calendar year, in addition to locally observed public holidays. [1]

Requests must be submitted through the HR portal **at least 3 days before** the intended leave date. Your direct manager approves the request and it is recorded automatically in the HR system. [2]

A few additional details worth knowing:

- Up to **5 unused days** carry over into the next calendar year and expire at the end of March.
- Sick leave (14 days) is tracked separately and is never deducted from annual leave.

If you need to book time off in the next week, flag it with your manager directly — the 3-day notice window is the only hard requirement.`,
        citations: citationsLeave,
        createdAt: iso({ hours: 3 }),
        model: "gpt-4o-mini",
        latencyMs: 812,
        tokenCount: 268,
        feedback: null,
      },
      {
        id: "m3",
        role: "user",
        content: "Does that include public holidays?",
        createdAt: iso({ hours: 3, minutes: 4 }),
      },
      {
        id: "m4",
        role: "assistant",
        content: `Yes — public holidays observed in your country of employment are **in addition to** the 20 annual leave days, so they are not deducted from your balance. [1]

The handbook does not list the holiday calendar itself; that lives in the HR portal under *Company calendar*.`,
        citations: [citationsLeave[0]],
        createdAt: iso({ hours: 3, minutes: 4 }),
        model: "gpt-4o-mini",
        latencyMs: 604,
        tokenCount: 96,
        feedback: null,
      },
    ],
  },
  {
    id: "conv_hr",
    title: "HR handbook",
    collectionId: "col_hr",
    updatedAt: iso({ days: 1 }),
    messageCount: 2,
    messages: [
      {
        id: "m1",
        role: "user",
        content: "Summarise the parental leave policy.",
        createdAt: iso({ days: 1 }),
      },
      {
        id: "m2",
        role: "assistant",
        content: `Primary caregivers receive **16 weeks of fully paid parental leave**. Secondary caregivers receive **4 weeks**, which may be taken any time within the first 12 months after birth or adoption. [1]`,
        citations: [citationsLeave[1]],
        createdAt: iso({ days: 1 }),
        model: "gpt-4o-mini",
        latencyMs: 733,
        tokenCount: 74,
        feedback: null,
      },
    ],
  },
  {
    id: "conv_fin",
    title: "Financial report",
    collectionId: "col_fin",
    updatedAt: iso({ days: 3 }),
    messageCount: 2,
    messages: [
      {
        id: "m1",
        role: "user",
        content: "What were Q3 operating expenses and our cash position?",
        createdAt: iso({ days: 3 }),
      },
      {
        id: "m2",
        role: "assistant",
        content: demoAnswers[2].content,
        citations: demoAnswers[2].citations,
        createdAt: iso({ days: 3 }),
        model: "gpt-4o-mini",
        latencyMs: 921,
        tokenCount: 312,
        feedback: null,
      },
    ],
  },
];

export const suggestedQuestions = [
  "How many days of annual leave do we get?",
  "What is the incident severity process?",
  "Summarise Q3 operating expenses",
  "Who can access restricted documents?",
];
