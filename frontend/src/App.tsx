import "./App.css";
import Hero from "./components/Hero";
import PublicDataNotice from "./components/PublicDataNotice";
import ServerStatus from "./components/ServerStatus";
import AccessSessionSection from "./features/session/AccessSessionSection";
import { useBackendHealth } from "./hooks/useBackendHealth";

/** Composes Ludex's hero and browser-authorized Steam experience. */
function App() {
   const connectionState = useBackendHealth();

   return (
      <div className="app">
         <ServerStatus connectionState={connectionState} />
         <main className="app__content">
            <Hero />
            <AccessSessionSection />
            <PublicDataNotice />
         </main>
         <footer className="app__footer" aria-label="Site information">
            <a href="#privacy-data">Privacy &amp; data use</a>
            <span aria-hidden="true">•</span>
            <a href="https://steamcommunity.com/dev/apiterms">Steam Web API</a>
            <span aria-hidden="true">•</span>
            <a href="https://www.igdb.com/">Game metadata from IGDB</a>
         </footer>
      </div>
   );
}

export default App;
