<script lang="ts">
  import { base } from '$app/paths';
</script>

<svelte:head>
  <title>Privacy Policy — Erallie's Song List</title>
  <meta name="description" content="Privacy Policy for Erallie's Song List, operated by Gozar Productions LLC." />
</svelte:head>

<section class="page-intro">
  <div>
    <div class="eyebrow">Legal</div>
    <h1 id="privacy-policy"><a class="legal-heading-link" href={`${base}/privacy#privacy-policy`}>Privacy Policy</a></h1>
    <p class="lede">How Erallie's Song List handles account and song-request information.</p>
  </div>
</section>

<article class="panel legal-document">
  <p class="legal-updated"><strong>Last updated:</strong> September 5, 2026</p>

  <p>Gozar Productions LLC (“Gozar Productions,” “we,” “us,” or “our”) operates Erallie's Song List at songlist.gozarproductions.com and its supporting queue API (together, the “Service”). This policy explains the information processed when you browse the Service, sign in, link an account, or request a song.</p>

  <h2 id="information-we-process"><a class="legal-heading-link" href={`${base}/privacy#information-we-process`}>Information We Process</a></h2>
  <h3 id="account-information"><a class="legal-heading-link" href={`${base}/privacy#account-information`}>Account information</a></h3>
  <p>When you sign in with Twitch, Discord, or Google, the provider sends us information authorized through its sign-in process. The Service stores the provider name, your provider-specific user ID, display name, profile-image URL, and authorization tokens. Depending on the provider and permissions shown during sign-in, the provider may also make basic account or email information available. We do not receive or store your provider password.</p>

  <h3 id="song-requests-and-queue-activity"><a class="legal-heading-link" href={`${base}/privacy#song-requests-and-queue-activity`}>Song requests and queue activity</a></h3>
  <p>When you request a song, we process your selected song, request display name, request time, queue status, and an internal account identifier. Your request display name and selected song are sent to MustardMine and shown in the public request queue. If you request through Twitch commands, the Service may use your Twitch display name to recognize which queue entries you may remove.</p>

  <h3 id="cookies-and-local-storage"><a class="legal-heading-link" href={`${base}/privacy#cookies-and-local-storage`}>Cookies and local storage</a></h3>
  <ul>
    <li><strong>Session cookie:</strong> the essential <code>queue_tracker_session</code> cookie keeps you signed in. It is HTTP-only and is configured to expire after 30 days. The server stores a hash of its random value rather than the cookie value itself.</li>
    <li><strong>Theme preference:</strong> the Service stores your light- or dark-mode choice in your browser's local storage under <code>isDarkMode</code>. If you have not chosen a theme, the site follows your device preference.</li>
  </ul>

  <h3 id="technical-information"><a class="legal-heading-link" href={`${base}/privacy#technical-information`}>Technical information</a></h3>
  <p>Our hosting, security, and server infrastructure may process standard request information such as IP address, browser or device information, requested pages, timestamps, referring site, and error or security events. This information may appear in operational logs used to secure and troubleshoot the Service.</p>

  <h2 id="how-we-use-information"><a class="legal-heading-link" href={`${base}/privacy#how-we-use-information`}>How We Use Information</a></h2>
  <p>We use the information described above to:</p>
  <ul>
    <li>authenticate you and link the providers you choose;</li>
    <li>select your request name, with Twitch preferred over Discord and Discord over Google;</li>
    <li>submit, display, update, and remove eligible song requests;</li>
    <li>identify the requests you are allowed to remove;</li>
    <li>maintain song history and administer the Service; and</li>
    <li>protect, operate, diagnose, and improve reliability and security.</li>
  </ul>
  <p>We do not sell personal information or use it for targeted advertising.</p>

  <h2 id="when-information-is-shared"><a class="legal-heading-link" href={`${base}/privacy#when-information-is-shared`}>When Information Is Shared</a></h2>
  <p>We share or allow processing only as needed to operate the Service:</p>
  <ul>
    <li><strong>Twitch, Discord, and Google</strong> provide sign-in and account-linking services. Review the <a href="https://www.twitch.tv/p/en/legal/privacy-notice/" target="_blank" rel="noopener noreferrer">Twitch Privacy Notice</a>, <a href="https://discord.com/privacy" target="_blank" rel="noopener noreferrer">Discord Privacy Policy</a>, and <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google Privacy Policy</a>.</li>
    <li><strong>MustardMine</strong> receives the song and request name needed to add or remove a queue entry; those details are visible in its queue. Review <a href="https://mustardmine.com/privacytos" target="_blank" rel="noopener noreferrer">MustardMine's Privacy Policy and Terms of Service</a>.</li>
    <li><strong>GitHub Pages</strong> hosts the public website, and <strong>Cloudflare</strong> provides networking, security, and access to the queue API. Review the <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" target="_blank" rel="noopener noreferrer">GitHub General Privacy Statement</a> and <a href="https://www.cloudflare.com/policies/privacy/" target="_blank" rel="noopener noreferrer">Cloudflare Privacy Policy</a>.</li>
    <li>We may disclose information when required by law or when reasonably necessary to protect users, the Service, or our legal rights.</li>
  </ul>
  <p>We do not control these third parties' independent processing. Their own terms and privacy policies apply when you use their services.</p>

  <h2 id="retention-security-and-deletion"><a class="legal-heading-link" href={`${base}/privacy#retention-security-and-deletion`}>Retention, Security, and Deletion</a></h2>
  <p>We retain linked identity information and authorization tokens while the identity remains linked or as otherwise needed to operate the Service. Tokens are encrypted at rest, and the Service uses access controls and encrypted network connections where supported. No online system can be guaranteed completely secure.</p>
  <p>Signing out ends the current browser session but does not delete linked identities. You can disconnect an identity from the Account page. Disconnecting your final identity deletes your Queue Tracker account, linked identity records, stored tokens, and active sessions. Historical request records may retain the requested song, request display name, time, and status after their internal association with your deleted account is removed. Operational logs and backups, if any, may remain for a limited period before deletion or replacement.</p>

  <h2 id="your-choices-and-rights"><a class="legal-heading-link" href={`${base}/privacy#your-choices-and-rights`}>Your Choices and Rights</a></h2>
  <p>You may disconnect linked providers from the Account page, clear the theme preference through browser storage controls, delete cookies, or revoke the Service's access through the relevant provider's account settings. Clearing the session cookie signs you out.</p>
  <p>Depending on where you live, you may have rights to request access to, correction of, deletion of, or restriction or objection to certain processing of your information. We may need enough information to verify your identity before acting on a request.</p>

  <h2 id="children-and-international-processing"><a class="legal-heading-link" href={`${base}/privacy#children-and-international-processing`}>Children and International Processing</a></h2>
  <p>The Service is intended for a general audience and is not directed to children under 13. You must also meet the minimum age and other requirements of any sign-in provider you use. Information may be processed in the United States and in locations where our service providers operate.</p>

  <h2 id="changes"><a class="legal-heading-link" href={`${base}/privacy#changes`}>Changes</a></h2>
  <p>We may update this policy as the Service, its providers, or legal requirements change. The date at the top shows the latest revision.</p>

  <h2 id="contact"><a class="legal-heading-link" href={`${base}/privacy#contact`}>Contact</a></h2>
  <p>For questions or privacy requests, email <a href="mailto:contact@gozarproductions.com">contact@gozarproductions.com</a> and include enough information for us to identify the relevant account.</p>
</article>
