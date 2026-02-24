import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="dashboard-header">
      <div className="header-left">
        <h1>GPU Server Reservation</h1>
        <nav className="header-nav">
          <NavLink to="/" className="header-link" end>예약</NavLink>
          <NavLink to="/gpu-health" className="header-link">GPU 헬스</NavLink>
          <NavLink to="/feedback" className="header-link">의견 게시판</NavLink>
          {user?.role === 'admin' && (
            <>
              <NavLink to="/servers" className="header-link">서버 관리</NavLink>
              <NavLink to="/users" className="header-link">사용자 관리</NavLink>
              <NavLink to="/session-logs" className="header-link">세션 로그</NavLink>
            </>
          )}
        </nav>
      </div>
      <div className="header-right">
        <span className="user-info">
          {user?.name}
          <span className={`role-badge role-${user?.role ?? 'user'}`} title="권한">
            {user?.role === 'admin' ? '관리자' : '일반 사용자'}
          </span>
        </span>
        <button type="button" className="btn btn-secondary" onClick={logout}>
          Logout
        </button>
      </div>
    </header>
  );
}
