import "./public-data-notice.css";

/** Publishes Ludex's public-profile, retention, and provider-use boundaries. */
function PublicDataNotice() {
   return (
      <section
         className="public-data-notice"
         id="privacy-data"
         aria-labelledby="privacy-data-heading"
      >
         <p className="public-data-notice__eyebrow">Public portfolio notice</p>
         <h2 id="privacy-data-heading">Privacy &amp; Data Use</h2>
         <p>
            Ludex is an independent portfolio project. Visitors may use its
            owner-authorized cached sample library or submit a public Steam
            profile. Starting the cached sample does not contact Steam;
            explicitly refreshing a library does.
         </p>

         <div className="public-data-notice__sections">
            <section aria-labelledby="privacy-data-collected">
               <h3 id="privacy-data-collected">What is used</h3>
               <p>
                  Ludex may request and cache the submitted Steam ID, public
                  display name, profile and avatar URLs, owned games, playtime,
                  and last-played information. Shared game facts and artwork may
                  be cached from IGDB. The owner-authorized sample exposes the
                  same cached profile and library fields even while its source
                  Steam profile is private. Recommendation preferences are used
                  for the current request and are not saved as a user account.
                  For abuse prevention, raw network addresses are used
                  transiently by in-memory limits but are not persisted or
                  application-logged; durable limits use keyed opaque buckets.
               </p>
            </section>

            <section aria-labelledby="privacy-data-access">
               <h3 id="privacy-data-access">Access &amp; cookies</h3>
               <p>
                  A required, secure, HTTP-only cookie authorizes this browser
                  to one cached profile for a fixed seven days. Ludex stores
                  only a one-way digest of its random session token. The cookie
                  is not Steam login, and a submitted Steam ID is not proof of
                  account ownership. Ludex uses no advertising or analytics
                  cookies.
               </p>
            </section>

            <section aria-labelledby="privacy-data-retention">
               <h3 id="privacy-data-retention">Storage &amp; retention</h3>
               <p>
                  Application data, PostgreSQL data, and encrypted backups are
                  kept in the United States. Ending a session revokes browser
                  access immediately. Profile-specific data becomes eligible for
                  operator cleanup when no session remains active and at least
                  30 days have passed since the latest session ended. Encrypted
                  recovery backups may retain deleted profile data for up to
                  approximately 58 days after that session ended.
               </p>
            </section>

            <section aria-labelledby="privacy-data-providers">
               <h3 id="privacy-data-providers">Providers &amp; availability</h3>
               <p>
                  Steam data, provider integrations, and Ludex are provided
                  as-is and as-available, without warranties. Ludex is not
                  affiliated with or endorsed by Valve, Steam, IGDB, or Twitch.
                  Recommendation and refinement requests use cached facts and do
                  not contact those providers.
               </p>
            </section>
         </div>
      </section>
   );
}

export default PublicDataNotice;
