import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router";
import { ClaimPage } from "./ClaimPage";
import { InstructionsPage } from "./InstructionsPage";
import { QueuePage } from "./QueuePage";

function Header() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <header className="header">
      <div className="brand">
        <h1>UnderCover</h1>
        <p className="tagline">Travel claims</p>
      </div>
      <nav className="nav">
        <NavLink to="/">Queue</NavLink>
        <NavLink to="/instructions">Instructions</NavLink>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setTheme(theme === "dark" ? "light" : "dark");
          }}
        >
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </nav>
    </header>
  );
}

export function App() {
  return (
    <div className="shell">
      <Header />
      <Routes>
        <Route path="/" element={<QueuePage />} />
        <Route path="/claims/:claimId" element={<ClaimPage />} />
        <Route path="/instructions" element={<InstructionsPage />} />
      </Routes>
    </div>
  );
}
