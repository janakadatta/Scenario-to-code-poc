# Design Documentation

## Entity-Relationship Diagram

```mermaid
erDiagram
    SCHEME {
        string schemeId PK
        string schemeName
        string schemeType
        string status
        date startDate
        date createdDate
    }

    EMPLOYER {
        string employerId PK
        string schemeId FK
        string companyName
        string taxRegistrationNumber
        string contactEmail
        string status
        date onboardingDate
    }

    MEMBER {
        string memberId PK
        string employerId FK
        string nationalId
        string firstName
        string lastName
        string email
        date dateOfBirth
        string status
        date joinDate
    }

    PENSION_ACCOUNT {
        string accountId PK
        string memberId FK
        string schemeId FK
        string accountNumber
        double currentBalance
        string currency
        string accountStatus
        date createdDate
    }

    CONTRIBUTION {
        string contributionId PK
        string accountId FK
        string employerId FK
        double employerAmount
        double memberAmount
        double totalAmount
        string payPeriod
        string status
        date contributionDate
    }

    INVESTMENT_PORTFOLIO {
        string portfolioId PK
        string accountId FK
        string fundName
        double allocatedUnits
        double unitValue
        double totalValue
        date lastValuationDate
    }

    BENEFIT_PAYMENT {
        string benefitId PK
        string accountId FK
        string memberId FK
        string claimType
        double requestedAmount
        double approvedAmount
        string status
        date requestDate
        date paymentDate
    }

    AUDIT_LOG {
        string logId PK
        string entityName
        string entityId
        string action
        string performedBy
        date timestamp
        string details
    }

    SCHEME ||--|{ EMPLOYER : "sponsors"
    SCHEME ||--|{ PENSION_ACCOUNT : "governs"
    EMPLOYER ||--|{ MEMBER : "employs"
    MEMBER ||--|| PENSION_ACCOUNT : "owns"
    PENSION_ACCOUNT ||--|{ CONTRIBUTION : "receives"
    PENSION_ACCOUNT ||--|{ INVESTMENT_PORTFOLIO : "holds"
    PENSION_ACCOUNT ||--|{ BENEFIT_PAYMENT : "disburses"
```

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Emp as Employer Admin
    participant UI as Angular Frontend
    participant GW as API Gateway
    participant ES as Employer Service
    participant MS as Member Service
    participant CS as Contribution Service
    participant IS as Investment Service
    participant DB as MongoDB Cluster

    Emp->>UI: Submit Employer Onboarding & Bulk Member Data
    UI->>GW: POST /api/v1/employers/onboard (Employer + Member List)
    GW->>ES: Route Onboard Request
    ES->>DB: Save Employer Document
    DB-->>ES: Employer Created
    ES->>MS: Trigger Bulk Member Enrollment (employerId, memberList)
    
    loop For each member in list
        MS->>DB: Insert Member Document
        MS->>DB: Initialize Pension Account (Balance: 0.0)
    end
    MS-->>ES: Enrollment Completed
    ES-->>GW: Onboarding Success Response
    GW-->>UI: 201 Created (Employer & Members Active)
    UI-->>Emp: Display Onboarding Dashboard

    Note over Emp, IS: Monthly Contribution Processing Flow

    Emp->>UI: Upload Monthly Contribution Schedule
    UI->>GW: POST /api/v1/contributions/batch
    GW->>CS: Route Contribution Batch Request
    CS->>DB: Save Contribution Records (Status: PENDING)
    CS->>CS: Validate Amounts against Member Pension Accounts
    CS->>DB: Update Pension Accounts (Increase Balance)
    CS->>IS: Request Auto-Investment Allocation (accountId, amount)
    IS->>DB: Purchase Fund Units & Update Investment Portfolio
    IS-->>CS: Investment Allocated
    CS->>DB: Update Contribution Record (Status: PROCESSED)
    CS-->>GW: Batch Processing Complete Response
    GW-->>UI: Display Batch Success Summary
```

## High-Level Design

High-Level Design (HLD) Document - Pension Scheme Setup Platform

1. Architecture Overview
The Pension Scheme Setup Platform uses a cloud-native, microservices-based architecture running on Kubernetes. The platform separates presentation, API gateway, core domain microservices, and persistence layers to ensure high availability (99.5%), horizontal scalability, and multi-tenant security across employers and members.

2. Component Details
- Frontend Layer: Angular single-page application (SPA) providing self-service interfaces for Administrators, Employers, and Members.
- Gateway Layer: Spring Cloud Gateway acting as the API Gateway handling Routing, OAuth2/OIDC JWT Authentication, Rate Limiting, and CORS management.
- Backend Services Layer (Java 25 Spring Boot):
  - Scheme Service: Manages pension scheme configurations, rules, and governance.
  - Employer Service: Handles employer onboarding and verification workflows.
  - Member Service: Manages member registration, demographic data, and account linking.
  - Pension Account Service: Handles account creation, balance updates, and account state transitions.
  - Contribution Service: Manages batch contribution files, validation, and posting.
  - Investment Service: Tracks fund unit valuations, allocations, and portfolios.
  - Benefit Service: Processes claims, eligibility verification, and disbursement requests.
  - Reporting & Audit Service: Generates real-time compliance reporting and central audit logs.
- Persistence Layer: MongoDB Enterprise / Mongo Atlas cluster utilizing document collections optimized for scheme domain aggregates.
- Infrastructure & Platform: Docker containers orchestrated via Kubernetes (EKS/GKE), with automated CI/CD pipelines deploying immutable artifacts.

3. System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client_Layer ["Client Layer (Angular SPA)"]
        UI_Admin["Admin Portal"]
        UI_Emp["Employer Portal"]
        UI_Mem["Member Portal"]
    end

    subgraph Security_Gateway ["API Gateway & Security"]
        GW["Spring Cloud Gateway / OAuth2 OIDC"]
    end

    subgraph Backend_Services ["Microservices Layer (Java 25 / Spring Boot)"]
        SchemeSvc["Scheme Service"]
        EmpSvc["Employer Service"]
        MemSvc["Member Service"]
        AcctSvc["Pension Account Service"]
        ContribSvc["Contribution Service"]
        InvestSvc["Investment Service"]
        BenefitSvc["Benefit Service"]
        AuditSvc["Reporting & Audit Service"]
    end

    subgraph Persistence_Layer ["Data Layer"]
        DB[(MongoDB Cluster)]
    end

    UI_Admin --> GW
    UI_Emp --> GW
    UI_Mem --> GW

    GW --> SchemeSvc
    GW --> EmpSvc
    GW --> MemSvc
    GW --> AcctSvc
    GW --> ContribSvc
    GW --> InvestSvc
    GW --> BenefitSvc
    GW --> AuditSvc

    SchemeSvc --> DB
    EmpSvc --> DB
    MemSvc --> DB
    AcctSvc --> DB
    ContribSvc --> DB
    InvestSvc --> DB
    BenefitSvc --> DB
    AuditSvc --> DB
```

4. Out-of-Scope Integration Boundaries
Payroll systems, tax processing engines, banking payment clearing rails, and actuarial modeling engines are external downstream systems interacting asynchronously via REST API webhooks or file exchanges.

## Low-Level Design

Low-Level Design (LLD) Document - Pension Scheme Setup Platform

1. Key Microservice Modules & Java Class Responsibilities

1.1 Employer Service (`com.pension.employer`)
- `EmployerController`: REST entry point for onboarding and employer management.
- `EmployerService`: Business logic for employer validation, tax ID verification, and state transition.
- `EmployerRepository`: Spring Data MongoDB repository managing `Employer` documents.
- `Employer`: Domain entity representing corporate sponsors.

1.2 Member & Account Service (`com.pension.member`)
- `MemberController`: Exposes endpoints for bulk enrollment and profile updates.
- `MemberService`: Manages member records, checks duplicate national IDs, and triggers account creation.
- `PensionAccountService`: Generates unique account numbers, handles credit/debit operations on balances.
- `MemberRepository`, `PensionAccountRepository`: Spring Data MongoDB repositories.

1.3 Contribution Service (`com.pension.contribution`)
- `ContributionController`: Exposes API for manual schedule entry and batch CSV/JSON uploads.
- `ContributionProcessor`: Orchestrates batch validation, balance crediting, and investment trigger.
- `ContributionRepository`: Spring Data MongoDB repository for contribution records.

1.4 Investment Service (`com.pension.investment`)
- `InvestmentController`: Exposes fund allocation and valuation queries.
- `InvestmentService`: Calculates portfolio units based on fund NAV and allocates contributions.
- `InvestmentRepository`: Mongo repository for investment portfolio documents.

1.5 Benefit Service (`com.pension.benefit`)
- `BenefitController`: Handles benefit claim submissions and status tracking.
- `BenefitService`: Validates account balances, rules, and prepares disbursement payloads.

2. Critical Java Class Implementations (Sample Schematics)

```java
// Java 25 Domain Document
package com.pension.contribution.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import java.math.BigDecimal;
import java.time.Instant;

@Document(collection = "contributions")
public record Contribution(
    @Id String contributionId,
    String accountId,
    String employerId,
    BigDecimal employerAmount,
    BigDecimal memberAmount,
    BigDecimal totalAmount,
    String payPeriod,
    ContributionStatus status,
    Instant contributionDate
) {}

public enum ContributionStatus { PENDING, PROCESSED, FAILED }
```

```java
// Spring Boot Service Layer
package com.pension.contribution.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ContributionService {
    private final ContributionRepository contributionRepository;
    private final PensionAccountService accountService;
    private final InvestmentService investmentService;

    public ContributionService(ContributionRepository contributionRepository, 
                               PensionAccountService accountService, 
                               InvestmentService investmentService) {
        this.contributionRepository = contributionRepository;
        this.accountService = accountService;
        this.investmentService = investmentService;
    }

    @Transactional
    public ContributionResponse processContribution(ContributionRequest request) {
        // Validate and save initial record
        Contribution entry = contributionRepository.save(request.toEntity());
        
        // Update account balance
        accountService.creditBalance(entry.accountId(), entry.totalAmount());
        
        // Trigger auto-allocation in investments
        investmentService.allocateFunds(entry.accountId(), entry.totalAmount());
        
        Contribution processed = contributionRepository.save(entry.withStatus(ContributionStatus.PROCESSED));
        return ContributionResponse.fromEntity(processed);
    }
}
```

3. Core REST API Operations Specification

3.1 Employer Management API
- `POST /api/v1/employers`
  - Request: `{ "companyName": "Acme Corp", "taxId": "TAX12345", "schemeId": "SCH-001", "contactEmail": "hr@acme.com" }`
  - Response: `201 Created` -> `{ "employerId": "EMP-9901", "status": "ACTIVE" }`
- `GET /api/v1/employers/{employerId}`
  - Response: `200 OK` -> Returns detailed employer entity.

3.2 Member Enrollment API
- `POST /api/v1/employers/{employerId}/members/batch`
  - Request: List of member entities (National ID, Name, Email, DOB).
  - Response: `207 Multi-Status` / `200 OK` -> `{ "totalProcessed": 150, "failed": 0 }`

3.3 Contribution Management API
- `POST /api/v1/contributions/batch`
  - Request: `{ "employerId": "EMP-9901", "payPeriod": "2026-03", "schedules": [ { "accountId": "ACC-100", "employerAmount": 500.00, "memberAmount": 250.00 } ] }`
  - Response: `202 Accepted` -> `{ "batchId": "BAT-8821", "status": "PROCESSING" }`

3.4 Benefit Claims API
- `POST /api/v1/benefits/claims`
  - Request: `{ "memberId": "MEM-501", "accountId": "ACC-100", "claimType": "RETIREMENT", "requestedAmount": 50000.00 }`
  - Response: `201 Created` -> `{ "claimId": "CLM-301", "status": "UNDER_REVIEW" }`
