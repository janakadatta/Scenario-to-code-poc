# Design Documentation

## Entity-Relationship Diagram

```mermaid
erDiagram
    CUSTOMER {
        uuid id PK
        string name
        string email UK
        string phone_number
        string shipping_address
        datetime created_at
    }

    PRODUCT {
        uuid id PK
        string name
        string description
        decimal price
        int stock_quantity
        datetime updated_at
    }

    ORDER {
        uuid id PK
        uuid customer_id FK
        string status
        decimal total_amount
        datetime order_date
        datetime updated_at
    }

    ORDER_ITEM {
        uuid id PK
        uuid order_id FK
        uuid product_id FK
        int quantity
        decimal unit_price
    }

    CUSTOMER ||--o{ ORDER : "places"
    ORDER ||--|{ ORDER_ITEM : "contains"
    PRODUCT ||--o{ ORDER_ITEM : "referenced in"
```

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Customer
    participant Gateway as API Gateway / Auth
    participant OrderSvc as Order Service
    participant InventorySvc as Inventory Service
    participant DB as Database

    Customer->>Gateway: POST /api/v1/orders (Items, Quantities)
    Gateway->>Gateway: Authenticate JWT & extract Customer ID
    Gateway->>OrderSvc: CreateOrder(CustomerID, Items)
    
    OrderSvc->>DB: Begin Transaction
    
    loop Validate Stock for Each Item
        OrderSvc->>InventorySvc: CheckAndLockStock(ProductID, Quantity)
        InventorySvc->>DB: SELECT stock_quantity FROM Product WHERE id = ? FOR UPDATE
        alt Insufficient Stock
            DB-->>InventorySvc: Stock < Requested Quantity
            InventorySvc-->>OrderSvc: Insufficient Stock Failure
            OrderSvc->>DB: Rollback Transaction
            OrderSvc-->>Gateway: Order Rejected Error (Out of Stock)
            Gateway-->>Customer: 400 Bad Request ("Product X is out of stock")
        else Stock Available
            InventorySvc-->>OrderSvc: Stock Confirmed
        end
    end

    loop Deduct Stock for Each Item
        OrderSvc->>InventorySvc: DeductStock(ProductID, Quantity)
        InventorySvc->>DB: UPDATE Product SET stock_quantity = stock_quantity - qty WHERE id = ?
    end

    OrderSvc->>DB: INSERT into Order & OrderItem tables (Status = 'PLACED')
    OrderSvc->>DB: Commit Transaction
    
    OrderSvc-->>Gateway: Order Created Confirmation (Order ID, Details)
    Gateway-->>Customer: 201 Created (Order Response Payload)
```

## High-Level Design

# High-Level Design (HLD) - Order Management System

## System Overview
The Order Management System (OMS) is structured as a resilient, service-oriented backend architecture designed to handle transactionally safe e-commerce operations. It ensures reliable inventory locking, data consistency, multi-role authentication, and high throughput.

## Core Architectural Components

1. **API Gateway & Identity Provider**:
   - Handles SSL termination, rate limiting, and request routing.
   - Validates JSON Web Tokens (JWT) for authentication.
   - Enforces Role-Based Access Control (RBAC): `ROLE_CUSTOMER` vs `ROLE_ADMIN`.

2. **Order Service**:
   - Manages order lifecycles (creation, status updates, user order queries).
   - Coordinates order creation workflows and status state machine validations.

3. **Inventory / Product Service**:
   - Maintains catalog items and stock levels.
   - Handles stock reservation and restoration under strict ACID isolation levels to prevent race conditions (overselling).

4. **Customer Service**:
   - Manages customer profile data and ensures global uniqueness of email addresses.

5. **Database Layer (Relational DB - PostgreSQL)**:
   - Stores transactional data. Utilizes row-level locking (`FOR UPDATE`) during order processing to maintain strict inventory integrity.

## System Architecture Diagram

```mermaid
flowchart TD
    Client[Client Applications: Web / Mobile]
    APIGW[API Gateway & Auth Module]
    
    subgraph Core Services Layer
        CustomerSvc[Customer Service]
        OrderSvc[Order Service]
        ProductSvc[Product & Inventory Service]
    end

    Database[(Relational Database\nPostgreSQL)]

    Client -->|HTTPS / REST API| APIGW
    APIGW -->|Authenticate & Route| CustomerSvc
    APIGW -->|Authenticate & Route| OrderSvc
    APIGW -->|Authenticate & Route| ProductSvc

    OrderSvc -->|Verify & Reserve Stock| ProductSvc
    CustomerSvc -->|Read/Write| Database
    OrderSvc -->|Read/Write Orders| Database
    ProductSvc -->|Update Stock| Database
```

## Strategy for Key Technical Requirements

- **Concurrency & Stock Integrity**: Stock deduction is wrapped inside a database transaction using pessimistic locking (`SELECT ... FOR UPDATE`) or atomic SQL execution (`UPDATE products SET stock_quantity = stock_quantity - QTY WHERE id = ID AND stock_quantity >= QTY`) to eliminate race conditions.
- **Order Cancellation**: Cancelling an order (permitted only in `PLACED` status) executes an atomic increment to restore stock (`UPDATE products SET stock_quantity = stock_quantity + QTY`).
- **Pagination**: All listing APIs enforce default and maximum page sizes using standardized limit-offset query parameters.

## Low-Level Design

# Low-Level Design (LLD) - Order Management System

## Key Modules and Responsibilities

### 1. `CustomerModule`
- **CustomerController**: Handles profile retrieval and customer registration.
- **CustomerService**: Enforces unique email constraint check prior to persistence.
- **CustomerRepository**: Interacts with the database for `Customer` entity management.

### 2. `ProductModule`
- **ProductController**: Provides endpoints to browse products with pagination and update products.
- **ProductService**: Manages inventory balances and pricing constraints (`price > 0`).
- **ProductRepository**: Performs database operations on products including row locking for inventory operations.

### 3. `OrderModule`
- **OrderController**: Handles order placement, cancellation, status changes, and order retrieval.
- **OrderService**: Implements the order lifecycle state machine, coordinates transactional stock checks, stock deductions, and stock restorations.
- **OrderRepository**: Manages persistence for `Order` and `OrderItem` records.

---

## State Machine: Order Status Lifecycle

Valid transitions:
- `PLACED` -> `CONFIRMED` (Admin action)
- `PLACED` -> `CANCELLED` (Customer or Admin action; triggers stock restoration)
- `CONFIRMED` -> `SHIPPED` (Admin action)
- `SHIPPED` -> `DELIVERED` (Admin action)

Attempting any illegal state transition (e.g., `SHIPPED` -> `CANCELLED`) throws an `InvalidStateTransitionException`.

---

## API Specifications

All list responses return a standard Paginated Wrapper:
```json
{
  "content": [...],
  "page": 0,
  "size": 20,
  "totalElements": 100,
  "totalPages": 5
}
```

### Endpoints

#### Product APIs
- **`GET /api/v1/products?page=0&size=20&sort=name,asc`**
  - **Access**: Public / Authenticated
  - **Description**: List products with pagination.

- **`POST /api/v1/products`**
  - **Access**: Admin (`ROLE_ADMIN`)
  - **Payload Validation**: `price > 0`, `stock_quantity >= 0`.

#### Order APIs
- **`POST /api/v1/orders`**
  - **Access**: Authenticated Customer (`ROLE_CUSTOMER`)
  - **Description**: Places a new order. Automatically binds customer identity from JWT.
  - **Request Body**:
    ```json
    {
      "items": [
        { "productId": "uuid", "quantity": 2 }
      ]
    }
    ```
  - **Validation Rules**: Each `quantity` must be >= 1. Checks stock availability; if any item is short on stock, aborts transaction and returns `400 Bad Request`.

- **`GET /api/v1/orders/me?page=0&size=10`**
  - **Access**: Authenticated Customer (`ROLE_CUSTOMER`)
  - **Description**: Lists authenticated customer's past orders with pagination.

- **`GET /api/v1/orders?page=0&size=20`**
  - **Access**: Admin (`ROLE_ADMIN`)
  - **Description**: Lists all customer orders across the system with pagination.

- **`GET /api/v1/orders/{id}`**
  - **Access**: Admin or Order Owner
  - **Description**: Fetches single order details and line items.

- **`PATCH /api/v1/orders/{id}/status`**
  - **Access**: Admin (`ROLE_ADMIN`)
  - **Request Body**: `{ "status": "SHIPPED" }`
  - **Description**: Updates order status following state transition rules.

- **`POST /api/v1/orders/{id}/cancel`**
  - **Access**: Authenticated Customer (Owner) or Admin
  - **Description**: Cancels order.
  - **Business Rules**:
    - Rejects request with `400 Bad Request` if current status is not `PLACED`.
    - Updates order status to `CANCELLED`.
    - Automatically restores product stock quantities in a single transaction.
