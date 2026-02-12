# 관리자 계정 기능 설계 (Design Guide 산출물)

## 1. 요구사항 정리

- **현재**: 회원가입 시 일반 사용자(role=user)만 가입 가능 (DB default 유지).
- **목표**:
  - 최초 관리자(admin)를 안전하게 생성할 수 있는 방법 제공.
  - 관리자가 사용자 목록 조회·역할(role) 변경·계정 비활성화(is_active) 가능.

**가정**: 일반 회원가입(register)은 계속 일반 사용자만 생성. 관리자 계정은 “최초 시드” 또는 “기존 관리자의 승격”으로만 생성.

---

## 2. 아키텍처

```
[클라이언트]
  - 일반 사용자: 예약, 의견, 로그아웃
  - 관리자: 위 + 사용자 관리 페이지 (/users)

[Backend]
  - 기존 Auth API: 변경 없음 (register → role=user 유지).
  - 신규 Users API (admin only):
    GET  /api/v1/users        → 목록 (pagination)
    PATCH /api/v1/users/{id} → role, is_active 변경
  - 최초 관리자: 앱 기동 시 admin 0명 && ADMIN_EMAIL/ADMIN_PASSWORD 설정 시 1명 생성 (lifespan seed).
```

**패턴**: 레이어드 API, 기존 deps.get_current_admin 재사용, 시드 로직은 기존 seed_default_server_resource와 동일한 lifespan 패턴.

---

## 3. 세분화된 작업 목록

| # | 작업 | 의존성 | 비고 |
|---|------|--------|------|
| 1 | config에 ADMIN_EMAIL, ADMIN_PASSWORD (optional) 추가 | - | .env.example 문서화 |
| 2 | lifespan에서 최초 관리자 시드 (admin 0명일 때만) | 1 | User 모델, AuthService 또는 직접 생성 |
| 3 | Users 스키마 (UserListResponse, UserUpdateRequest) | - | id, email, name, role, is_active, created_at |
| 4 | Users API 라우터 (GET list, PATCH update) | 3, deps.get_current_admin | 본인 강등 방지: admin 1명이면 role 변경 불가 |
| 5 | main.py에 users_router 등록 | 4 | - |
| 6 | Frontend: api client에 usersAPI (list, update) | - | - |
| 7 | Frontend: AdminRoute (role===admin만 허용) | - | PrivateRoute 내부 또는 별도 |
| 8 | Frontend: UsersPage (목록, 역할/활성 토글) | 6, 7 | - |
| 9 | App 라우트 및 네비(관리자만 “사용자 관리” 링크) | 7, 8 | - |

---

## 4. 개발 가이드 (구현 순서)

1. **Backend config** → ADMIN_EMAIL, ADMIN_PASSWORD 추가.
2. **Backend seed** → lifespan에서 admin 수 0이고 env 설정돼 있으면 해당 계정으로 admin 생성.
3. **Backend schemas** → user list/update용 Pydantic 모델.
4. **Backend users router** → GET /users, PATCH /users/{id}, get_current_admin 의존.
5. **Backend main** → include_router(users_router).
6. **Frontend client** → usersAPI.list(), usersAPI.update(id, { role, is_active }).
7. **Frontend AdminRoute** → useAuth().user?.role === 'admin' ? children : Navigate to /.
8. **Frontend UsersPage** → 테이블, 역할 셀렉트, 활성 토글, API 호출.
9. **Frontend App** → Route /users + 헤더에 admin일 때만 “사용자 관리” 링크.

---

## 5. 참고 패턴/원칙

- **최초 관리자**: 환경변수 기반 시드 (많은 SaaS에서 사용). 비밀번호는 env에만, 로그에서는 제외.
- **역할 변경 제한**: 마지막 admin은 강등 불가 (데드락 방지).
- **기존 아키텍처 정합성**: ARCHITECTURE.md의 Auth/Resources 권한 패턴과 동일 (get_current_admin).
