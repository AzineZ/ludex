import "./App.css";
import Hero from "./components/Hero";
import ProfilesSection from "./features/profiles/ProfilesSection";
import { useBackendHealth } from "./hooks/useBackendHealth";

/** Composes Ludex's hero and local Steam-profile experience. */
function App() {
   const connectionState = useBackendHealth();

   return (
      <main className="app">
         <section className="app__content">
            <Hero connectionState={connectionState} />
            <ProfilesSection />
         </section>
      </main>
   );
}

export default App;
