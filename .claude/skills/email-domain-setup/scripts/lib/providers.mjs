// Préréglages par fournisseur d'envoi. Une seule source de vérité partagée
// par dns-plan.mjs (génération) et dns-audit.mjs (vérification).
// Les valeurs entre <chevrons> sont des jetons propres à chaque domaine :
// ils viennent de l'API du fournisseur et ne doivent jamais être inventés.
//
// Champs :
//   spfInclude     mécanisme à inclure dans le SPF du domaine d'enveloppe (null = aucun SPF à publier)
//   spfOn          "return-path" (SPF sur le sous-domaine MAIL FROM), "from" (sur le domaine d'envoi) ou "none"
//   returnPath     { label, type: "mx"|"cname", mx(region) → string|string[], target }
//   dkim           { kind: "txt"|"cname"|"ses-easy", selectors (pour l'audit), records(domain) }
//   verification   enregistrement de preuve de propriété éventuel
//   tracking       domaine de suivi des liens (optionnel)
//   regions        régions disponibles (null = pas de choix)

const sesFeedback = (region) => `feedback-smtp.${region}.amazonses.com`;

export const PROVIDERS = {
  // Resend = SES en coulisses. Return-Path configurable (custom_return_path, défaut "send",
  // non modifiable ensuite). DKIM 1024 bits uniquement, sans rotation documentée.
  resend: {
    label: "Resend",
    docs: "https://resend.com/docs/dashboard/domains/introduction",
    regions: ["us-east-1", "eu-west-1", "sa-east-1", "ap-northeast-1"],
    defaultRegion: "eu-west-1",
    spfInclude: "amazonses.com",
    spfOn: "return-path",
    returnPath: { label: "send", type: "mx", mx: sesFeedback, priority: 10 },
    dkim: {
      kind: "txt",
      selectors: ["resend"],
      records: (d) => [{ type: "TXT", name: `resend._domainkey.${d}`, value: "<p=… clé publique fournie par Resend>", purpose: "dkim" }],
    },
    tracking: { label: "links", type: "cname", target: "links1.resend-dns.com" },
  },

  // SES v2 : Easy DKIM = 3 CNAME vers <token>.<SigningHostedZone> (la zone varie selon la
  // région et l'identité : la lire dans GetEmailIdentity). Clé 2048 bits par défaut.
  // MAIL FROM : sous-domaine libre (Lumail "ses", ici "bounce"), un seul MX.
  ses: {
    label: "Amazon SES",
    docs: "https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication.html",
    regions: ["us-east-1", "us-east-2", "us-west-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1", "eu-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-south-1", "ca-central-1", "sa-east-1"],
    defaultRegion: "eu-west-3",
    spfInclude: "amazonses.com",
    spfOn: "return-path",
    returnPath: { label: "bounce", type: "mx", mx: sesFeedback, priority: 10 },
    dkim: {
      kind: "ses-easy",
      selectors: [],
      records: (d) => [1, 2, 3].map((i) => ({
        type: "CNAME", name: `<token${i}>._domainkey.${d}`, value: `<token${i}>.<SigningHostedZone>`, purpose: "dkim",
      })),
    },
  },

  // Brevo : sans « branded subdomain », le Return-Path reste brevosend.com →
  // SPF non aligné, DMARC repose sur DKIM seul. SPF/MX ne sont fournis que pour
  // une IP dédiée. Ancien format : TXT mail._domainkey (1024 bits).
  brevo: {
    label: "Brevo",
    docs: "https://help.brevo.com/hc/en-us/articles/12163873383186",
    regions: null,
    spfInclude: "spf.brevo.com",
    spfOn: "none",
    returnPath: null,
    verification: (d) => ({ type: "TXT", name: d, value: "brevo-code:<code fourni par Brevo>", purpose: "verification" }),
    dkim: {
      kind: "cname",
      selectors: ["brevo1", "brevo2", "mail"],
      records: (d) => [1, 2].map((i) => ({
        type: "CNAME", name: `brevo${i}._domainkey.${d}`, value: `b${i}.<valeur fournie par Brevo>.dkim.brevo.com`, purpose: "dkim",
      })),
    },
    dmarcRua: "rua@dmarc.brevo.com",
  },

  // Postmark : le CNAME de Return-Path porte le SPF (aucun include à ajouter).
  // DKIM 1024 bits, sélecteur horodaté, rotation via POST /domains/{id}/rotatedkim.
  postmark: {
    label: "Postmark",
    docs: "https://postmarkapp.com/support/article/1046-how-do-i-add-dkim-and-return-path-records",
    regions: null,
    spfInclude: null,
    spfOn: "return-path",
    returnPath: { label: "pm-bounces", type: "cname", target: "pm.mtasv.net" },
    dkim: {
      kind: "txt",
      selectors: [],
      records: (d) => [{ type: "TXT", name: `<AAAAMMJJhhmmss>pm._domainkey.${d}`, value: "<k=rsa;p=… fourni par Postmark>", purpose: "dkim" }],
    },
  },

  // Mailgun : le domaine enregistré (ex. mg.client.com) sert aussi d'enveloppe.
  // « Automatic Sender Security » = 2 CNAME pdk1/pdk2 (2048 bits, rotation 120 j).
  mailgun: {
    label: "Mailgun",
    docs: "https://documentation.mailgun.com/docs/mailgun/user-manual/domains/domains-verify",
    regions: ["us", "eu"],
    defaultRegion: "eu",
    spfInclude: "mailgun.org",
    spfOn: "from",
    returnPath: null,
    dkim: {
      kind: "cname",
      selectors: [],
      records: (d) => [1, 2].map((i) => ({
        type: "CNAME", name: `pdk${i}._domainkey.${d}`, value: `pdk${i}._domainkey.<id>.dkim1.mailgun.com`, purpose: "dkim",
      })),
    },
    inboundMx: (region) => (region === "eu" ? ["mxa.eu.mailgun.org", "mxb.eu.mailgun.org"] : ["mxa.mailgun.org", "mxb.mailgun.org"]),
    tracking: { label: "email", type: "cname", target: "mailgun.org", targetEu: "eu.mailgun.org" },
  },

  // SendGrid « automated security » : tout en CNAME vers u<id>.wl<id>.sendgrid.net.
  sendgrid: {
    label: "SendGrid",
    docs: "https://www.twilio.com/docs/sendgrid/ui/account-and-settings/how-to-set-up-domain-authentication",
    regions: ["global", "eu"],
    defaultRegion: "global",
    spfInclude: "sendgrid.net",
    spfOn: "return-path",
    returnPath: { label: "<em1234>", type: "cname", target: "<u1234567.wl123>.sendgrid.net" },
    dkim: {
      kind: "cname",
      selectors: ["s1", "s2"],
      records: (d) => ["s1", "s2"].map((s) => ({
        type: "CNAME", name: `${s}._domainkey.${d}`, value: `${s}.domainkey.<u1234567.wl123>.sendgrid.net`, purpose: "dkim",
      })),
    },
    tracking: { label: "<url1234>", type: "cname", target: "sendgrid.net" },
  },

  scaleway: {
    label: "Scaleway Transactional Email",
    docs: "https://www.scaleway.com/en/docs/transactional-email/how-to/authenticate-domain/",
    regions: ["fr-par"],
    defaultRegion: "fr-par",
    spfInclude: "_spf.tem.scaleway.com",
    spfOn: "from",
    returnPath: null,
    dkim: {
      kind: "txt",
      selectors: [],
      records: (d) => [{ type: "TXT", name: `<project_id>._domainkey.${d}`, value: "<clé fournie dans dkim_config>", purpose: "dkim" }],
    },
  },

  mailjet: {
    label: "Mailjet",
    docs: "https://dev.mailjet.com/docs/email-api/senders-domains/spf-dkim-validation",
    regions: null,
    spfInclude: "spf.mailjet.com",
    spfOn: "from",
    returnPath: null,
    verification: (d) => ({ type: "TXT", name: `<OwnerShipTokenRecordName>.${d}`, value: "<OwnerShipToken>", purpose: "verification" }),
    dkim: {
      kind: "txt",
      selectors: ["mailjet"],
      records: (d) => [{ type: "TXT", name: `mailjet._domainkey.${d}`, value: "<k=rsa; p=… fourni par Mailjet>", purpose: "dkim" }],
    },
  },

  // Cloudflare Email Service (bêta, DNS Cloudflare obligatoire, records ajoutés automatiquement).
  cloudflare: {
    label: "Cloudflare Email Service",
    docs: "https://developers.cloudflare.com/email-service/configuration/domains/",
    regions: null,
    spfInclude: "_spf.mx.cloudflare.net",
    spfOn: "return-path",
    returnPath: { label: "cf-bounce", type: "mx", mx: () => ["route1.mx.cloudflare.net", "route2.mx.cloudflare.net", "route3.mx.cloudflare.net"], priority: 10 },
    dkim: {
      kind: "txt",
      selectors: ["cf-bounce"],
      records: (d) => [{ type: "TXT", name: `cf-bounce._domainkey.${d}`, value: "<clé publiée par Cloudflare>", purpose: "dkim" }],
    },
  },

  // Boîtes Google Workspace / Microsoft 365 (envoi « humain », lemlist, cold email).
  google: {
    label: "Google Workspace",
    docs: "https://support.google.com/a/answer/174124",
    regions: null,
    spfInclude: "_spf.google.com",
    spfOn: "from",
    returnPath: null,
    dkim: {
      kind: "txt",
      selectors: ["google"],
      records: (d) => [{ type: "TXT", name: `google._domainkey.${d}`, value: "v=DKIM1; k=rsa; p=<clé générée dans la console Admin>", purpose: "dkim" }],
    },
  },
  microsoft: {
    label: "Microsoft 365",
    docs: "https://learn.microsoft.com/defender-office-365/email-authentication-dkim-configure",
    regions: null,
    spfInclude: "spf.protection.outlook.com",
    spfOn: "from",
    returnPath: null,
    dkim: {
      kind: "cname",
      selectors: ["selector1", "selector2"],
      records: (d) => [1, 2].map((i) => ({
        type: "CNAME", name: `selector${i}._domainkey.${d}`, value: `<cible selector${i} copiée depuis Microsoft Defender>`, purpose: "dkim",
      })),
    },
  },

  generic: {
    label: "Générique (SMTP / autre ESP)",
    docs: null,
    regions: null,
    spfInclude: "<include du fournisseur>",
    spfOn: "return-path",
    returnPath: { label: "bounce", type: "mx", mx: () => "<serveur bounce du fournisseur>", priority: 10 },
    dkim: {
      kind: "txt",
      selectors: [],
      records: (d) => [{ type: "TXT", name: `<selecteur>._domainkey.${d}`, value: "v=DKIM1; k=rsa; p=<clé publique 2048 bits>", purpose: "dkim" }],
    },
  },
};

export function returnPathHost(provider, domain) {
  if (!provider?.returnPath) return null;
  return `${provider.returnPath.label}.${domain}`;
}

export const mxList = (provider, region) => [provider.returnPath.mx(region)].flat();
