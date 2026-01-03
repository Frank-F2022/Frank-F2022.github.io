# [Project Name] - Project Website

This is the official project website for [Project Name]. The website is built with pure HTML, CSS, and JavaScript for optimal performance and easy deployment.

## Structure

```
EgoGrasp.io/
├── index.html          # Main HTML file
├── css/
│   └── style.css       # Stylesheet
├── js/
│   └── main.js         # JavaScript interactions
├── assets/
│   ├── images/         # Image assets
│   │   ├── pipeline.png
│   │   └── results/
│   └── videos/         # Video demos
└── README.md
```

## Customization Guide

### 1. Update Content

Replace all placeholders in `index.html`:

- `[Project Title]` - Your paper title
- `[Author X]` - Author names
- `[Institution X]` - Institution names
- `[Paper Description]` - Abstract paragraphs
- `[Feature X]` - Key features
- `[Method Component X]` - Method descriptions
- `[GitHub URL]` - Your repository URL
- `[Contact Email]` - Contact information

### 2. Add Media Assets

**Images:**
- Place pipeline diagram at: `assets/images/pipeline.png`
- Add result visualizations in: `assets/images/results/`

**Videos:**
- Add demo videos in: `assets/videos/`
- Update video placeholders in HTML with actual video elements:

```html
<video controls width="100%">
    <source src="assets/videos/demo.mp4" type="video/mp4">
</video>
```

### 3. Update Links

- Paper PDF: Update href in "Paper" button
- GitHub: Update href in "Code" button
- Video: Update href in "Video" button (or link to YouTube)

### 4. Customize Colors

Edit CSS variables in `css/style.css`:

```css
:root {
    --primary-color: #2563eb;    /* Main brand color */
    --secondary-color: #10b981;  /* Accent color */
    --text-dark: #1f2937;        /* Dark text */
    --text-light: #6b7280;       /* Light text */
}
```

## Deployment

### GitHub Pages

1. Push to GitHub repository
2. Go to Settings > Pages
3. Select branch (usually `main`) and root directory
4. Save and wait for deployment
5. Access at: `https://[username].github.io/[repo-name]`

### Custom Domain

1. Add `CNAME` file with your domain
2. Configure DNS settings with your domain provider
3. Point to GitHub Pages IP addresses

### Alternative Hosting

- **Netlify**: Drag and drop folder or connect GitHub
- **Vercel**: Import GitHub repository
- **AWS S3**: Upload files and enable static website hosting

## Features

- Responsive design (mobile, tablet, desktop)
- Smooth scrolling navigation
- Copy-to-clipboard for code blocks
- Fade-in animations on scroll
- Active navigation highlighting
- Optimized for performance

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers

## License

[Add your license information]

## Contact

[Add contact information]
