import ludexLogo from "../assets/ludex_logo.png";
import type { ConnectionState } from "../hooks/useBackendHealth";

type HeroProps = {
   connectionState: ConnectionState;
};

/** Displays Ludex's branding and backend connection state. */
function Hero({ connectionState }: HeroProps) {
   return (
      <>
         <header className="app__hero">
            <h1 className="app__logo-heading">
               <img
                  className="app__logo"
                  src={ludexLogo}
                  alt="Ludex — Your next game awaits"
               />
            </h1>
            <p className="app__intro">
               Ludex helps you choose what to play from your existing Steam
               library.
            </p>

            <p className={`app__status app__status--${connectionState}`}>
               Backend: {connectionState}
            </p>
         </header>
      </>
   );
}

export default Hero;
