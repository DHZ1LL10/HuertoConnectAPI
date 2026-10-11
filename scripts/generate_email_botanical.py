"""Generate lightweight original botanical email artwork (no remote assets)."""
from pathlib import Path
from PIL import Image, ImageDraw
import math

DEST = Path(__file__).resolve().parents[1] / "auth-service/app/assets"


def curve(draw, points, color, width):
    a, b, c, d = points
    samples = []
    for i in range(81):
        t = i / 80
        samples.append(tuple((1-t)**3*a[j] + 3*(1-t)**2*t*b[j] + 3*(1-t)*t*t*c[j] + t**3*d[j] for j in (0, 1)))
    draw.line(samples, fill=color, width=width)


def roots(draw, x, y, color, scale=1):
    for direction in (-1, 1):
        for i in range(4):
            reach = (80 + i*55)*scale
            end = (x + direction*reach, y + (30+i*12)*scale)
            curve(draw, [(x,y), (x+direction*30*scale,y+40*scale), (end[0]-direction*35*scale,end[1]-20*scale), end], color, 3)
            for k in (0.45, 0.75):
                bx = x + direction*reach*k
                by = y + (30+i*12)*scale*k
                curve(draw, [(bx,by), (bx+direction*10,by+12), (bx+direction*4,by+24), (bx+direction*20,by+33)], color, 2)


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    hero = Image.new("RGBA", (1120, 620), (0,0,0,0))
    d = ImageDraw.Draw(hero)
    ivory = "#f6f5dd"
    def leaf(x, y, angle, length=23):
        # Pointed leaves, rather than simple circles: a botanical silhouette.
        points=[]
        for side in (1,-1):
            for i in range(21):
                t=i/20 if side==1 else 1-i/20
                along=t*length
                across=side*math.sin(math.pi*t)*length*.28
                points.append((x+along*math.cos(angle)-across*math.sin(angle),y+along*math.sin(angle)+across*math.cos(angle)))
        d.polygon(points,fill=ivory)
    def branch(x, y, angle, length, depth, leafy=True):
        ex=x+math.cos(angle)*length
        ey=y+math.sin(angle)*length
        width=max(1,depth*2 if leafy else depth)
        curve(d,[(x,y),(x+math.cos(angle+.12)*length*.35,y+math.sin(angle+.12)*length*.35),(x+math.cos(angle-.12)*length*.7,y+math.sin(angle-.12)*length*.7),(ex,ey)],ivory,width)
        if depth<=1:
            if leafy:
                leaf(ex,ey,angle,21)
                leaf(x+(ex-x)*.55,y+(ey-y)*.55,angle+.8,17)
            return
        branch(ex,ey,angle-.5,length*.7,depth-1,leafy)
        branch(ex,ey,angle+.47,length*.72,depth-1,leafy)
    # Crown and trunk echo the reference; roots fan out beneath a small pot.
    curve(d,[(560,335),(558,260),(545,190),(560,100)],ivory,15)
    for side in (-1,1):
        for y,length,angle in ((290,95,-.35),(245,90,-.65),(195,72,-.85)):
            branch(560,y,angle if side==1 else -math.pi-angle,length,4)
    branch(560,150,-math.pi/2,57,3)
    d.line((195,338,487,338),fill="#c8d4aa",width=2)
    d.line((633,338,925,338),fill="#c8d4aa",width=2)
    d.polygon([(512,348),(608,348),(594,409),(526,409)],fill="#d8ad75")
    d.rounded_rectangle((501,333,619,354),5,fill="#eed2a4")
    d.line((515,340,605,340),fill=ivory,width=2)
    for side in (-1,1):
        for angle,length in ((.35,105),(.65,90),(1.05,80)):
            branch(560,409,angle if side==1 else math.pi-angle,length,5,False)
    branch(560,409,math.pi/2,65,4,False)
    hero.save(DEST / "maceta_raices.png", optimize=True)
    separator=Image.new("RGBA",(1120,170),(0,0,0,0))
    d=ImageDraw.Draw(separator)
    for side in (-1,1):
        for angle in (.2,.6,1.0):
            branch(560,0,angle if side==1 else math.pi-angle,66,4,False)
    separator.save(DEST / "raices.png",optimize=True)
    # Use the very same branching as the tree, along the full email frame.
    frame=Image.new("RGBA",(1120,1800),(0,0,0,0))
    d=ImageDraw.Draw(frame)
    ivory="#b7c99a"
    for x,side in ((35,1),(1085,-1)):
        curve(d,[(x,0),(x+side*22,550),(x-side*20,1250),(x,1800)],ivory,3)
        for y in range(100,1700,200):
            branch(x,y,.55 if side==1 else math.pi-.55,95,5,False)
            branch(x,y+60,1.0 if side==1 else math.pi-1.0,62,4,False)
    frame.save(DEST / "raices_marco.png",optimize=True)
    print("Botanical email assets generated")


if __name__ == "__main__":
    main()
