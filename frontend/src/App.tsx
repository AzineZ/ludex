import "./App.css";
import Hero from "./components/Hero";
import PublicDataNotice from "./components/PublicDataNotice";
import ServerStatus from "./components/ServerStatus";
import AccessSessionSection from "./features/session/AccessSessionSection";
import { useBackendHealth } from "./hooks/useBackendHealth";

/** Composes Ludex's hero and browser-authorized Steam experience. */
function ExperiencePage() {
   const connectionState = useBackendHealth();

   return (
      <div className="app">
         <ServerStatus connectionState={connectionState} />
         <main className="app__content">
            <Hero />
            <AccessSessionSection />
         </main>
         <SiteFooter />
      </div>
   );
}

function PrivacyPage() {
   return (
      <div className="app app--privacy">
         <main className="app__privacy-content">
            <a className="app__privacy-back" href="/">
               ← Back to Ludex
            </a>
            <PublicDataNotice />
         </main>
         <SiteFooter />
      </div>
   );
}

function SiteFooter() {
   return (
      <footer className="app__footer" aria-label="Site information">
         <a href="/privacy">Privacy &amp; Data Use</a>
         <span aria-hidden="true">•</span>
         <a href="https://steamcommunity.com/dev/apiterms">Steam Web API</a>
         <span aria-hidden="true">•</span>
         <a href="https://www.igdb.com/">Game Metadata From IGDB</a>
      </footer>
   );
}

function App() {
   return window.location.pathname === "/privacy" ||
      window.location.pathname === "/privacy/" ? (
      <PrivacyPage />
   ) : (
      <ExperiencePage />
   );
}

export default App;
