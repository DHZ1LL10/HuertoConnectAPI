const fs = require('fs');
const path = require('path');
const { buildOtpEmailTemplate } = require('./src/templates/otp-email.template');

(async () => {
    const result = await buildOtpEmailTemplate({
        email: 'abiel.garcia@gmail.com',
        otpCode: '483921',
        expiresInMinutes: 5,
        verifyUrl: 'https://huertoconnect.com/login'
    });

    // For local preview, replace cid: with inline data URIs
    let html = result.html;
    for (const att of result.attachments) {
        const b64 = att.content.toString('base64');
        const dataUri = `data:${att.contentType};base64,${b64}`;
        html = html.replaceAll(`cid:${att.cid}`, dataUri);
    }

    fs.writeFileSync(path.join(__dirname, 'preview-email.html'), html, 'utf-8');

    // Log sizes
    const totalKB = result.attachments.reduce((s, a) => s + a.content.length, 0) / 1024;
    console.log(`Preview saved. ${result.attachments.length} PNG attachments (${totalKB.toFixed(1)} KB total)`);
    result.attachments.forEach(a => console.log(`  ${a.filename}: ${(a.content.length / 1024).toFixed(1)} KB`));
})();
