document.addEventListener("DOMContentLoaded", function() {
    // Inject Styles Programmatically - Using CSS Grid for Layout
    var style = document.createElement('style');
    style.innerHTML = `
        /* Linktree Icon Styling - Scale + Layout Adjustment */
        .md-footer-social__link[href*="linktr.ee"] {
            color: #43E660 !important;
            transform: scale(2.2);
            transform-origin: center;
            margin: 0 10px !important; 
        }
        .md-footer-social__link[href*="linktr.ee"]:hover {
            color: #2bb944 !important;
            transform: scale(2.4);
        }
        
        /* Grid Layout for Footer Meta */
        .md-footer-meta__inner {
            display: grid !important;
            grid-template-columns: 1fr minmax(250px, auto) !important;
            grid-template-rows: auto auto !important;
            align-items: start !important;
            gap: 0 20px !important;
        }
        
        /* Copyright section - Left column, spans both rows */
        .md-footer-copyright {
            grid-column: 1 !important;
            grid-row: 1 / 3 !important;
            width: auto !important;
            margin: 0 !important;
            padding: 0 !important;
            align-self: start !important;
            display: flex !important;
            align-items: center !important;
            height: 100% !important;
        }
        
        /* Social icons - Right column, first row */
        .md-social {
            grid-column: 2 !important;
            grid-row: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
            justify-self: end !important;
        }
        
        /* Made with text - Right column, second row */
        .made-with-custom {
            grid-column: 2 !important;
            grid-row: 2 !important;
            font-size: 0.7em !important;
            opacity: 0.6 !important;
            text-align: right !important;
            line-height: 1.2 !important;
            padding: 0 !important;
            width: auto !important;
            display: block !important;
            justify-self: end !important;
        }
    `;
    document.head.appendChild(style);
    
    // Create and insert the "Made with" text as a separate grid item
    var footerMeta = document.querySelector('.md-footer-meta__inner');
    if (footerMeta) {
        var madeWith = document.createElement('div');
        madeWith.className = 'made-with-custom';
        madeWith.innerHTML = 'Made with <a href="https://squidfunk.github.io/mkdocs-material/" target="_blank" rel="noopener">Material for MkDocs</a>';
        footerMeta.appendChild(madeWith);
        
        // Dynamically adjust margin based on social icons height
        setTimeout(function() {
            var socialIcons = document.querySelector('.md-social');
            if (socialIcons) {
                var iconsHeight = socialIcons.offsetHeight;
                var adjustedMargin = -(iconsHeight - 15); // 6px spacing from icons
                madeWith.style.marginTop = adjustedMargin + 'px';
            }
        }, 100); // Small delay to ensure elements are rendered
    }
});
