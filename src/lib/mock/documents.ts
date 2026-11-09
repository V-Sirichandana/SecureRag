import type { Collection, DocumentRecord } from "@/lib/types";
import { iso } from "./utils";

export const collections: Collection[] = [
  {
    id: "col_hr",
    name: "HR",
    description: "People policies, handbooks, onboarding and benefits documentation.",
    documentCount: 124,
    owner: "Sarah Johnson",
    updatedAt: iso({ hours: 2 }),
    visibility: "members",
    color: "#6366f1",
  },
  {
    id: "col_eng",
    name: "Engineering",
    description: "Architecture decision records, runbooks and platform documentation.",
    documentCount: 438,
    owner: "Alex Morgan",
    updatedAt: iso({ days: 1 }),
    visibility: "members",
    color: "#0ea5e9",
  },
  {
    id: "col_fin",
    name: "Finance",
    description: "Quarterly reports, budgets, procurement and expense policies.",
    documentCount: 87,
    owner: "Daniel Smith",
    updatedAt: iso({ days: 3 }),
    visibility: "restricted",
    color: "#16a34a",
  },
  {
    id: "col_sec",
    name: "Security",
    description: "Security policies, compliance evidence and incident response playbooks.",
    documentCount: 62,
    owner: "Vishvendra Vadla",
    updatedAt: iso({ days: 5 }),
    visibility: "restricted",
    color: "#f59e0b",
  },
];

export const documents: DocumentRecord[] = [
  {
    id: "doc_handbook",
    name: "Employee Handbook.pdf",
    fileType: "pdf",
    sizeBytes: 4_404_016,
    collectionId: "col_hr",
    collectionName: "HR",
    owner: "Sarah Johnson",
    department: "Human Resources",
    classification: "internal",
    status: "ready",
    createdAt: iso({ days: 120 }),
    updatedAt: iso({ hours: 2 }),
    pageCount: 48,
    chunkCount: 312,
    tags: ["policy", "onboarding"],
  },
  {
    id: "doc_architecture",
    name: "Engineering Architecture.pdf",
    fileType: "pdf",
    sizeBytes: 8_808_038,
    collectionId: "col_eng",
    collectionName: "Engineering",
    owner: "Alex Morgan",
    department: "Engineering",
    classification: "internal",
    status: "processing",
    createdAt: iso({ minutes: 10 }),
    updatedAt: iso({ minutes: 10 }),
    pageCount: 112,
    chunkCount: 0,
    tags: ["architecture", "platform"],
  },
  {
    id: "doc_security",
    name: "Security Policy.pdf",
    fileType: "pdf",
    sizeBytes: 2_198_016,
    collectionId: "col_sec",
    collectionName: "Security",
    owner: "Vishvendra Vadla",
    department: "Security",
    classification: "confidential",
    status: "ready",
    createdAt: iso({ days: 62 }),
    updatedAt: iso({ days: 5 }),
    pageCount: 26,
    chunkCount: 178,
    tags: ["compliance", "soc2"],
  },
  {
    id: "doc_financial",
    name: "Financial Report.pdf",
    fileType: "pdf",
    sizeBytes: 6_396_313,
    collectionId: "col_fin",
    collectionName: "Finance",
    owner: "Daniel Smith",
    department: "Finance",
    classification: "restricted",
    status: "ready",
    createdAt: iso({ days: 40 }),
    updatedAt: iso({ hours: 3 }),
    pageCount: 74,
    chunkCount: 401,
    tags: ["q3", "board"],
  },
  {
    id: "doc_prd",
    name: "Product Requirements.docx",
    fileType: "docx",
    sizeBytes: 1_310_720,
    collectionId: "col_eng",
    collectionName: "Engineering",
    owner: "Alex Morgan",
    department: "Product",
    classification: "internal",
    status: "ready",
    createdAt: iso({ days: 21 }),
    updatedAt: iso({ days: 4 }),
    pageCount: 32,
    chunkCount: 210,
    tags: ["roadmap"],
  },
  {
    id: "doc_hr_policy",
    name: "HR Policy.pdf",
    fileType: "pdf",
    sizeBytes: 918_528,
    collectionId: "col_hr",
    collectionName: "HR",
    owner: "Sarah Johnson",
    department: "Human Resources",
    classification: "internal",
    status: "ready",
    createdAt: iso({ days: 90 }),
    updatedAt: iso({ days: 12 }),
    pageCount: 18,
    chunkCount: 96,
    tags: ["leave", "policy"],
  },
  {
    id: "doc_vendor",
    name: "Vendor Risk Assessment.xlsx",
    fileType: "xlsx",
    sizeBytes: 742_400,
    collectionId: "col_sec",
    collectionName: "Security",
    owner: "Vishvendra Vadla",
    department: "Security",
    classification: "confidential",
    status: "failed",
    createdAt: iso({ days: 6 }),
    updatedAt: iso({ days: 6 }),
    pageCount: 0,
    chunkCount: 0,
    tags: ["vendors"],
  },
  {
    id: "doc_onboarding",
    name: "Onboarding Checklist.md",
    fileType: "md",
    sizeBytes: 32_768,
    collectionId: "col_hr",
    collectionName: "HR",
    owner: "Sarah Johnson",
    department: "Human Resources",
    classification: "public",
    status: "ready",
    createdAt: iso({ days: 14 }),
    updatedAt: iso({ days: 14 }),
    pageCount: 4,
    chunkCount: 22,
    tags: ["checklist"],
  },
  {
    id: "doc_infra",
    name: "Infrastructure Runbook.txt",
    fileType: "txt",
    sizeBytes: 128_904,
    collectionId: "col_eng",
    collectionName: "Engineering",
    owner: "Alex Morgan",
    department: "Engineering",
    classification: "internal",
    status: "archived",
    createdAt: iso({ days: 200 }),
    updatedAt: iso({ days: 45 }),
    pageCount: 60,
    chunkCount: 240,
    tags: ["runbook", "legacy"],
  },
  {
    id: "doc_budget",
    name: "FY27 Budget Draft.csv",
    fileType: "csv",
    sizeBytes: 89_000,
    collectionId: "col_fin",
    collectionName: "Finance",
    owner: "Daniel Smith",
    department: "Finance",
    classification: "restricted",
    status: "ready",
    createdAt: iso({ days: 9 }),
    updatedAt: iso({ days: 9 }),
    pageCount: 3,
    chunkCount: 15,
    tags: ["budget"],
  },
  {
    id: "doc_board",
    name: "Board Deck Q3.pptx",
    fileType: "pptx",
    sizeBytes: 15_990_784,
    collectionId: "col_fin",
    collectionName: "Finance",
    owner: "Daniel Smith",
    department: "Finance",
    classification: "restricted",
    status: "processing",
    createdAt: iso({ minutes: 45 }),
    updatedAt: iso({ minutes: 45 }),
    pageCount: 38,
    chunkCount: 0,
    tags: ["board"],
  },
  {
    id: "doc_incident",
    name: "Incident Response Playbook.pdf",
    fileType: "pdf",
    sizeBytes: 1_548_288,
    collectionId: "col_sec",
    collectionName: "Security",
    owner: "Vishvendra Vadla",
    department: "Security",
    classification: "confidential",
    status: "ready",
    createdAt: iso({ days: 33 }),
    updatedAt: iso({ days: 7 }),
    pageCount: 22,
    chunkCount: 130,
    tags: ["incident", "ir"],
  },
];

export interface DocumentPageContent {
  pageNumber: number;
  title: string;
  paragraphs: { id: string; text: string; highlight?: string }[];
}

export const documentPages: Record<string, DocumentPageContent[]> = {
  doc_handbook: [
    {
      pageNumber: 13,
      title: "Working Hours & Attendance",
      paragraphs: [
        {
          id: "p1",
          text: "Standard working hours are 9:00 to 18:00, Monday through Friday. Teams may agree flexible start and end times with their manager, provided core collaboration hours between 11:00 and 16:00 are covered.",
        },
        {
          id: "p2",
          text: "Remote work is permitted up to three days per week. Employees working fully remotely must have a documented home-office agreement on file.",
        },
      ],
    },
    {
      pageNumber: 14,
      title: "Annual Leave Policy",
      paragraphs: [
        {
          id: "p3",
          text: "Full-time employees are entitled to 20 days of annual leave per calendar year, in addition to public holidays observed in their country of employment.",
          highlight: "entitled to 20 days of annual leave",
        },
        {
          id: "p4",
          text: "Employees must submit leave requests at least 3 days before the intended leave date. Requests are approved by the direct manager and recorded in the HR system.",
          highlight: "at least 3 days before the intended leave date",
        },
        {
          id: "p5",
          text: "A maximum of 5 unused days may be carried into the following calendar year and must be used before the end of March.",
        },
      ],
    },
    {
      pageNumber: 15,
      title: "Sick Leave",
      paragraphs: [
        {
          id: "p6",
          text: "Employees are entitled to 14 days of paid sick leave annually. Absences longer than three consecutive days require a medical certificate.",
        },
        {
          id: "p7",
          text: "Sick leave is not deducted from the annual leave entitlement and does not carry over between years.",
        },
      ],
    },
  ],
  doc_hr_policy: [
    {
      pageNumber: 3,
      title: "Leave Request Procedure",
      paragraphs: [
        {
          id: "p1",
          text: "All leave requests must be submitted through the HR portal. Employees must submit leave requests at least 3 days before the intended leave date unless the request is due to an emergency.",
          highlight: "at least 3 days before the intended leave date",
        },
        {
          id: "p2",
          text: "Managers must respond to leave requests within two business days. Unresolved requests escalate automatically to the department head.",
        },
      ],
    },
    {
      pageNumber: 4,
      title: "Parental Leave",
      paragraphs: [
        {
          id: "p3",
          text: "Primary caregivers receive 16 weeks of fully paid parental leave. Secondary caregivers receive 4 weeks, which may be taken within the first 12 months after birth or adoption.",
        },
      ],
    },
  ],
  doc_financial: [
    {
      pageNumber: 22,
      title: "Operating Expenses",
      paragraphs: [
        {
          id: "p1",
          text: "Operating expenses for the quarter totalled $4.82M, an increase of 8.4% year over year, driven primarily by cloud infrastructure and headcount growth in engineering.",
          highlight: "totalled $4.82M",
        },
        {
          id: "p2",
          text: "Cloud spend was optimised by 12% after the migration to reserved instances, offsetting a portion of the headcount increase.",
        },
      ],
    },
    {
      pageNumber: 23,
      title: "Cash Position",
      paragraphs: [
        {
          id: "p3",
          text: "The company closed the quarter with $31.6M in cash and equivalents, providing 26 months of runway at the current burn rate.",
          highlight: "$31.6M in cash and equivalents",
        },
      ],
    },
  ],
  doc_security: [
    {
      pageNumber: 8,
      title: "Access Control",
      paragraphs: [
        {
          id: "p1",
          text: "Access to production systems is granted through role-based access control. All privileges are reviewed quarterly by the security team.",
          highlight: "role-based access control",
        },
        {
          id: "p2",
          text: "Multi-factor authentication is mandatory for all internal applications. Service accounts must use rotating credentials stored in the secrets manager.",
        },
      ],
    },
    {
      pageNumber: 11,
      title: "Data Classification",
      paragraphs: [
        {
          id: "p3",
          text: "Documents are classified as public, internal, confidential or restricted. Restricted data may only be shared with named individuals on a need-to-know basis.",
        },
      ],
    },
  ],
  doc_architecture: [
    {
      pageNumber: 5,
      title: "Retrieval Pipeline",
      paragraphs: [
        {
          id: "p1",
          text: "Documents are chunked at 512 tokens with a 64-token overlap, embedded, and indexed in the vector store. Retrieval uses hybrid search with reciprocal rank fusion before cross-encoder reranking.",
          highlight: "hybrid search with reciprocal rank fusion",
        },
        {
          id: "p2",
          text: "Every retrieval is scoped to the caller's tenant partition. Cross-tenant recall is prevented at the index level rather than filtered at query time.",
        },
      ],
    },
  ],
  doc_prd: [
    {
      pageNumber: 2,
      title: "Problem Statement",
      paragraphs: [
        {
          id: "p1",
          text: "Support engineers spend an average of 26 minutes locating the correct policy document for each escalation. A grounded assistant with citations should reduce this to under 5 minutes.",
          highlight: "reduce this to under 5 minutes",
        },
      ],
    },
  ],
  doc_incident: [
    {
      pageNumber: 4,
      title: "Severity Definitions",
      paragraphs: [
        {
          id: "p1",
          text: "Severity 1 incidents affect all customers and require an immediate page to the on-call engineer with a 15 minute acknowledgement target.",
          highlight: "15 minute acknowledgement target",
        },
      ],
    },
  ],
};

export function fallbackPages(name: string): DocumentPageContent[] {
  return [
    {
      pageNumber: 1,
      title: name.replace(/\.[^.]+$/, ""),
      paragraphs: [
        {
          id: "p1",
          text: "This document is part of the Acme Technologies knowledge base. Content is indexed and searchable through SecureRAG with citation support.",
        },
        {
          id: "p2",
          text: "Preview rendering is simulated in demo mode. Connect the FastAPI backend to stream real extracted pages.",
        },
      ],
    },
  ];
}
