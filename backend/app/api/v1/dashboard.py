import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.reservation import Reservation, ReservationStatus
from app.models.reservation_instance import ReservationInstance
from app.models.server_resource import ServerResource
from app.models.serve_case import ServeCase
from app.models.user import User
from app.schemas.dashboard import (
    GpuHealthResponse,
    ResourceStatus,
    ServerGpuHealth,
    ServerServeCaseSummary,
    StatusResponse,
    TimelineReservation,
    TimelineResource,
    TimelineResponse,
)
from app.schemas.reservation import ReservationListResponse, ReservationResponse
from app.services.gpu_health import collect_gpu_health, GpuHealthResult

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _instance_to_timeline(
    res: Reservation,
    inst: ReservationInstance,
    current_user_id: uuid.UUID,
) -> TimelineReservation:
    return TimelineReservation(
        id=inst.id,
        reservation_id=res.id,
        title=res.title,
        user_name=res.user.name if res.user else "Unknown",
        user_id=res.user_id,
        account_name=res.account_name,
        start_at=inst.start_at,
        end_at=inst.end_at,
        is_mine=res.user_id == current_user_id,
        status=inst.status.value,
    )


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    server_resource_ids: list[uuid.UUID] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a timeline view of reservations grouped by server resource."""
    resource_conditions = [ServerResource.is_active.is_(True)]
    if server_resource_ids:
        resource_conditions.append(ServerResource.id.in_(server_resource_ids))

    resources_result = await db.execute(
        select(ServerResource)
        .where(*resource_conditions)
        .order_by(ServerResource.name)
    )
    resources = list(resources_result.scalars().all())
    resource_ids = [r.id for r in resources]

    # instances 기준으로 시간 범위 필터링
    inst_result = await db.execute(
        select(ReservationInstance)
        .join(Reservation, Reservation.id == ReservationInstance.reservation_id)
        .options(selectinload(ReservationInstance.reservation).selectinload(Reservation.user))
        .where(
            ReservationInstance.server_resource_id.in_(resource_ids) if resource_ids else True,
            ReservationInstance.status.in_([ReservationStatus.ACTIVE, ReservationStatus.COMPLETED]),
            ReservationInstance.start_at < end_date,
            ReservationInstance.end_at > start_date,
        )
        .order_by(ReservationInstance.start_at)
    )
    instances = list(inst_result.scalars().all())

    # 서버별로 그룹핑
    reservation_map: dict[uuid.UUID, list[TimelineReservation]] = {}
    for inst in instances:
        res = inst.reservation
        timeline_res = _instance_to_timeline(res, inst, current_user.id)
        reservation_map.setdefault(inst.server_resource_id, []).append(timeline_res)

    timeline_resources = [
        TimelineResource(
            id=r.id,
            name=r.name,
            reservations=reservation_map.get(r.id, []),
        )
        for r in resources
    ]

    return TimelineResponse(resources=timeline_resources)


@router.get("/my-reservations", response_model=ReservationListResponse)
async def get_my_reservations(
    status: ReservationStatus | None = ReservationStatus.ACTIVE,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current user's reservations."""
    from app.services.reservation import ReservationService
    from sqlalchemy.orm import selectinload as sil
    from sqlalchemy import select as sel

    reservations, total = await ReservationService.list_reservations(
        db=db,
        user_id=current_user.id,
        status=status,
        limit=limit,
        offset=offset,
    )

    # instances 일괄 로드해서 start_at/end_at 채우기
    if reservations:
        rsv_ids = [r.id for r in reservations]
        inst_result = await db.execute(
            sel(ReservationInstance)
            .where(ReservationInstance.reservation_id.in_(rsv_ids))
            .order_by(ReservationInstance.start_at)
        )
        instances_by_rsv: dict[uuid.UUID, list[ReservationInstance]] = {}
        for inst in inst_result.scalars().all():
            instances_by_rsv.setdefault(inst.reservation_id, []).append(inst)
        for rsv in reservations:
            rsv.instances = instances_by_rsv.get(rsv.id, [])

    return ReservationListResponse(
        items=[ReservationResponse.model_validate(r) for r in reservations],
        total=total,
    )


@router.get("/status", response_model=StatusResponse)
async def get_server_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current status of all active server resources."""
    now = datetime.now(timezone.utc)

    resources_result = await db.execute(
        select(ServerResource)
        .where(ServerResource.is_active.is_(True))
        .order_by(ServerResource.name)
    )
    resources = list(resources_result.scalars().all())

    statuses = []
    for resource in resources:
        # 현재 진행 중인 instance
        current_result = await db.execute(
            select(ReservationInstance)
            .join(Reservation, Reservation.id == ReservationInstance.reservation_id)
            .options(selectinload(ReservationInstance.reservation).selectinload(Reservation.user))
            .where(
                ReservationInstance.server_resource_id == resource.id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
                ReservationInstance.start_at <= now,
                ReservationInstance.end_at > now,
            )
            .limit(1)
        )
        current_inst = current_result.scalar_one_or_none()

        # 다음 예정된 instance
        next_result = await db.execute(
            select(ReservationInstance)
            .join(Reservation, Reservation.id == ReservationInstance.reservation_id)
            .options(selectinload(ReservationInstance.reservation).selectinload(Reservation.user))
            .where(
                ReservationInstance.server_resource_id == resource.id,
                ReservationInstance.status == ReservationStatus.ACTIVE,
                ReservationInstance.start_at > now,
            )
            .order_by(ReservationInstance.start_at)
            .limit(1)
        )
        next_inst = next_result.scalar_one_or_none()

        if current_inst:
            current_status = "in_use"
        elif next_inst:
            current_status = "reserved"
        else:
            current_status = "available"

        def _to_timeline(inst: ReservationInstance | None) -> TimelineReservation | None:
            if inst is None:
                return None
            return _instance_to_timeline(inst.reservation, inst, current_user.id)

        statuses.append(
            ResourceStatus(
                id=resource.id,
                name=resource.name,
                current_status=current_status,
                current_reservation=_to_timeline(current_inst),
                next_reservation=_to_timeline(next_inst),
            )
        )

    return StatusResponse(resources=statuses)


@router.get("/gpu-health", response_model=GpuHealthResponse)
async def get_gpu_health(
    server_resource_id: uuid.UUID | None = Query(
        default=None, description="Filter by server resource ID"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get GPU usage for active servers with SSH."""
    conditions = [
        ServerResource.is_active.is_(True),
        ServerResource.host.isnot(None),
        ServerResource.ssh_username.isnot(None),
        ServerResource.ssh_private_key.isnot(None),
    ]
    if server_resource_id is not None:
        conditions.append(ServerResource.id == server_resource_id)

    result = await db.execute(
        select(ServerResource)
        .where(*conditions)
        .order_by(ServerResource.name)
    )
    resources = list(result.scalars().all())

    async def fetch_one(r: ServerResource) -> tuple[ServerResource, GpuHealthResult]:
        try:
            gpu_result = await collect_gpu_health(
                host=r.host or "",
                port=r.ssh_port,
                username=r.ssh_username or "",
                private_key=r.ssh_private_key,
            )
            return (r, gpu_result)
        except Exception as e:
            return (r, GpuHealthResult(ok=False, error_message=str(e), gpus=[], processes=[]))

    if not resources:
        return GpuHealthResponse(servers=[])

    gathered = await asyncio.gather(*[fetch_one(r) for r in resources])

    server_ids = [r.id for r in resources]
    cases_result = await db.execute(
        select(ServeCase)
        .where(ServeCase.server_resource_id.in_(server_ids))
        .order_by(ServeCase.created_at.desc())
    )
    all_cases = list(cases_result.scalars().all())
    cases_by_server: dict[uuid.UUID, list[ServeCase]] = {}
    for c in all_cases:
        if c.server_resource_id not in cases_by_server:
            cases_by_server[c.server_resource_id] = []
        if len(cases_by_server[c.server_resource_id]) < 5:
            cases_by_server[c.server_resource_id].append(c)

    servers_out: list[ServerGpuHealth] = []
    for item in gathered:
        r, gpu_result = item
        recent = [
            ServerServeCaseSummary(
                id=c.id,
                model_name=c.model_name,
                serve_command_preview=(c.serve_command or "")[:200],
                created_at=c.created_at,
            )
            for c in cases_by_server.get(r.id, [])
        ]
        servers_out.append(
            ServerGpuHealth(
                server_resource_id=r.id,
                server_name=r.name,
                ok=gpu_result.ok,
                error_message=gpu_result.error_message,
                gpus=gpu_result.gpus,
                processes=gpu_result.processes,
                recent_serve_cases=recent,
            )
        )
    return GpuHealthResponse(servers=servers_out)
