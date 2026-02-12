"""
Session Scheduler 테스트 스크립트

이 스크립트는 SessionScheduler의 기능을 수동으로 테스트합니다.

사용법:
    python -m scripts.test_session_scheduler
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.session_scheduler import SessionScheduler


async def test_process_events():
    """스케줄러 이벤트 처리 테스트"""
    print("=" * 60)
    print("Testing SessionScheduler.process_reservation_events()")
    print("=" * 60)
    
    result = await SessionScheduler.process_reservation_events()
    
    print("\n결과:")
    print(f"  타임스탬프: {result['timestamp']}")
    print(f"  활성화된 예약: {len(result['activated'])}개")
    print(f"  비활성화된 예약: {len(result['deactivated'])}개")
    print(f"  에러: {len(result['errors'])}개")
    
    if result['activated']:
        print("\n활성화된 예약:")
        for item in result['activated']:
            print(f"  - {item['reservation_id']}: {'성공' if item['success'] else '실패'}")
    
    if result['deactivated']:
        print("\n비활성화된 예약:")
        for item in result['deactivated']:
            print(f"  - {item['reservation_id']}: {'성공' if item['success'] else '실패'}")
    
    if result['errors']:
        print("\n에러 발생:")
        for error in result['errors']:
            print(f"  - {error.get('reservation_id', 'N/A')}: {error.get('error', 'Unknown error')}")
    
    print("\n" + "=" * 60)


async def main():
    """메인 함수"""
    try:
        await test_process_events()
    except KeyboardInterrupt:
        print("\n테스트 중단됨")
    except Exception as e:
        print(f"\n에러 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
