import "./App.css";
import Hero from "./components/Hero";
import ServerStatus from "./components/ServerStatus";
import AccessSessionSection from "./features/session/AccessSessionSection";
import { useBackendHealth } from "./hooks/useBackendHealth";

/** Composes Ludex's hero and browser-authorized Steam experience. */
function App() {
   const connectionState = useBackendHealth();

   return (
      <main className="app">
         <ServerStatus connectionState={connectionState} />
         <section className="app__content">
            <Hero />
            <AccessSessionSection />
         </section>
      </main>
   );
}

export default App;
