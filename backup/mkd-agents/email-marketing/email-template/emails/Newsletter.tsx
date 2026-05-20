import {
  Body,
  Container,
  Column,
  Head,
  Heading,
  Hr,
  Html,
  Img,
  Link,
  Preview,
  Row,
  Section,
  Text,
} from "@react-email/components";
import * as React from "react";

export interface Article {
  title: string;
  excerpt: string;
  link: string;
  thumbnail: string;
}

export interface NewsletterProps {
  date?: string;
  editorial?: string;
  articles?: Article[];
}

const DEFAULT_ARTICLES: Article[] = [
  {
    title: "Activation data marketing : comment exploiter vos fichiers clients pour maximiser vos campagnes",
    excerpt:
      "Vos bases de données clients dorment dans un CRM sous-exploité. Pendant ce temps, vos concurrents transforment leurs données en revenus. L'activation data marketing est la discipline qui convertit vos fichiers en performance commerciale réelle — désormais accessible aux équipes de toutes tailles.",
    link: "https://mkdgroupe.com/activation-data-marketing/",
    thumbnail: "https://ik.imagekit.io/rgpdsimplement/RDV.png?updatedAt=1769859349440",
  },
  {
    title: "RCS en France : 83% d'Éligibilité — Plus de 50 Millions de Smartphones Compatibles",
    excerpt:
      "Orange a récemment activé le RCS sur les iPhones avec iOS 18.4, rejoignant les autres opérateurs français. Le RCS enrichit les messages avec du contenu éditorialisé, un caractère sécurisé, et offre des fonctionnalités avancées par rapport au SMS traditionnel.",
    link: "https://mkdgroupe.com/rcs-en-france-eligibilite-83-pour-cent-50-millions-smartphones/",
    thumbnail: "https://mkdgroupe.com/wp-content/uploads/2025/08/thumbnail-72.jpeg",
  },
  {
    title: "Les Tendances du Marketing Digital en 2026 : Ce Que Vous Devez Savoir",
    excerpt:
      "Le monde du marketing digital évolue à une vitesse vertigineuse. En 2026, les marques qui réussissent sont celles qui ont su anticiper les grandes transformations technologiques et comportementales pour rester compétitives dans un environnement numérique en constante mutation.",
    link: "https://mkdgroupe.com/les-tendances-du-marketing-digital-en-2026-ce-que-vous-devez-savoir/",
    thumbnail:
      "https://mkdgroupe.com/wp-content/uploads/2026/03/hf_20260323_134146_3cf2da8b-22c4-4aeb-a2da-fcc226cc6714-scaled.png",
  },
];

const DEFAULT_EDITORIAL =
  "🚀 Data marketing, RCS & tendances 2026 : MKD Groupe vous dévoile 3 analyses clés pour booster vos campagnes. Ne manquez pas ! 📊✨";

export const Newsletter = ({
  date = new Date().toLocaleDateString("fr-FR", { year: "numeric", month: "long", day: "numeric" }),
  editorial = DEFAULT_EDITORIAL,
  articles = DEFAULT_ARTICLES,
}: NewsletterProps) => (
  <Html lang="fr" dir="ltr">
    <Head />
    <Preview>{editorial}</Preview>
    <Body style={body}>
      <Container style={container}>

        {/* HEADER */}
        <Section style={header}>
          <Row>
            <Column>
              <Img
                src="https://ik.imagekit.io/rgpdsimplement/footer.jpg"
                width="140"
                height="auto"
                alt="MKD Groupe"
                style={logo}
              />
            </Column>
            <Column align="right">
              <Text style={dateText}>{date}</Text>
            </Column>
          </Row>
        </Section>

        {/* EDITORIAL */}
        <Section style={editoSection}>
          <Text style={editoLabel}>ÉDITORIAL</Text>
          <Text style={editoText}>{editorial}</Text>
        </Section>

        <Hr style={divider} />

        {/* ARTICLES */}
        {articles.map((article, index) => (
          <React.Fragment key={index}>
            <Section style={articleSection}>
              <Row>
                <Column style={thumbnailColumn}>
                  <Img
                    src={article.thumbnail}
                    width="150"
                    height="auto"
                    alt={article.title}
                    style={thumbnail}
                  />
                </Column>
                <Column style={articleContent}>
                  <Heading as="h2" style={articleTitle}>
                    {article.title}
                  </Heading>
                  <Text style={articleExcerpt}>{article.excerpt}</Text>
                  <Link href={article.link} style={readMore}>
                    Lire l'article →
                  </Link>
                </Column>
              </Row>
            </Section>
            {index < articles.length - 1 && <Hr style={divider} />}
          </React.Fragment>
        ))}

        <Hr style={divider} />

        {/* FOOTER */}
        <Section style={footer}>
          <Img
            src="https://ik.imagekit.io/rgpdsimplement/header.png"
            width="120"
            height="auto"
            alt="MKD Groupe"
            style={footerLogo}
          />
          <Text style={footerText}>
            © {new Date().getFullYear()} MKD Groupe · Tous droits réservés
          </Text>
          <Text style={footerText}>
            MKD Groupe · 35 rue de la belle image, 94700 Maisons-Alfort
          </Text>
          <Text style={footerText}>
            📞 06 11 42 80 45 · ✉️{" "}
            <Link href="mailto:contact@mkdgroupe.com" style={footerLink}>
              contact@mkdgroupe.com
            </Link>
          </Text>
          <Text style={footerText}>
            <Link href="https://mkdgroupe.com/mentions-legales" style={footerLink}>
              Mentions légales
            </Link>
            {" · "}
            <Link href="{{{RESEND_UNSUBSCRIBE_URL}}}" style={footerLink}>
              Se désabonner
            </Link>
          </Text>
        </Section>

      </Container>
    </Body>
  </Html>
);

export default Newsletter;

// ─── Styles ──────────────────────────────────────────────────────────────────

const body: React.CSSProperties = {
  backgroundColor: "#f4f4f5",
  fontFamily: "'Inter', 'Helvetica Neue', Arial, sans-serif",
  margin: 0,
  padding: "32px 0",
};

const container: React.CSSProperties = {
  backgroundColor: "#ffffff",
  borderRadius: "8px",
  maxWidth: "600px",
  margin: "0 auto",
  overflow: "hidden",
  boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
};

const header: React.CSSProperties = {
  backgroundColor: "#ffffff",
  padding: "20px 32px",
  borderBottom: "3px solid #4E80A3",
};

const logo: React.CSSProperties = {
  display: "block",
};

const dateText: React.CSSProperties = {
  color: "#4E80A3",
  fontSize: "13px",
  fontWeight: "600",
  margin: 0,
  textAlign: "right" as const,
};

const editoSection: React.CSSProperties = {
  padding: "24px 32px 20px",
  backgroundColor: "#fafafa",
};

const editoLabel: React.CSSProperties = {
  color: "#4E80A3",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "1.5px",
  textTransform: "uppercase" as const,
  margin: "0 0 8px 0",
};

const editoText: React.CSSProperties = {
  color: "#1a1a2e",
  fontSize: "16px",
  lineHeight: "1.6",
  fontStyle: "italic",
  margin: 0,
};

const divider: React.CSSProperties = {
  borderColor: "#e5e7eb",
  margin: "0 32px",
};

const articleSection: React.CSSProperties = {
  padding: "24px 32px",
};

const thumbnailColumn: React.CSSProperties = {
  width: "160px",
  verticalAlign: "top",
  paddingRight: "20px",
};

const thumbnail: React.CSSProperties = {
  borderRadius: "6px",
  display: "block",
  width: "150px",
};

const articleContent: React.CSSProperties = {
  verticalAlign: "top",
};

const articleTitle: React.CSSProperties = {
  color: "#4E80A3",
  fontSize: "17px",
  fontWeight: "700",
  lineHeight: "1.4",
  margin: "0 0 10px 0",
};

const articleExcerpt: React.CSSProperties = {
  color: "#4b5563",
  fontSize: "14px",
  lineHeight: "1.6",
  margin: "0 0 12px 0",
};

const readMore: React.CSSProperties = {
  backgroundColor: "#4E80A3",
  borderRadius: "4px",
  color: "#ffffff",
  display: "inline-block",
  fontSize: "13px",
  fontWeight: "600",
  padding: "8px 16px",
  textDecoration: "none",
};

const footer: React.CSSProperties = {
  padding: "24px 32px",
  backgroundColor: "#f9fafb",
  textAlign: "center" as const,
};

const footerText: React.CSSProperties = {
  color: "#9ca3af",
  fontSize: "12px",
  lineHeight: "1.5",
  margin: "4px 0",
};

const footerLink: React.CSSProperties = {
  color: "#9ca3af",
  textDecoration: "underline",
};

const footerLogo: React.CSSProperties = {
  display: "block",
  margin: "0 auto 12px",
};
